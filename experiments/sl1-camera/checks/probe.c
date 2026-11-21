// SPDX-License-Identifier: MIT
// Bounded SL1 OV7251 optical check. No per-pixel output or frame files.
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <fcntl.h>
#include <linux/media.h>
#include <linux/media-bus-format.h>
#include <linux/v4l2-subdev.h>
#include <linux/videodev2.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <time.h>
#include <unistd.h>

enum { W=640,H=480,NB=4,NX=8,NY=6,NT=NX*NY,FRAMES=20,SKIP=8 };
struct record {uint32_t seq, timestamp_flags; long long ts; unsigned sum[NT],clip[NT];};
static struct record rows[3][FRAMES];
static volatile sig_atomic_t stopped;
static void interrupt(int s){stopped=s;}
static int ctl(int fd,unsigned long op,void *arg){
    int r; do r=ioctl(fd,op,arg);while(r<0 && errno==EINTR && !stopped);return r;
}
struct route {
    struct media_link_desc link;
    struct v4l2_subdev_format format;
    int changed_link,changed_format;
};
static int entity_id(const char *s,uint32_t *id){
    char *end;errno=0;unsigned long n=strtoul(s,&end,10);
    if(errno || !n || n>UINT32_MAX || *end || *s<'0' || *s>'9'){errno=EINVAL;return -1;}
    *id=n;return 0;
}
static int prepare_route(int media,int rx,uint32_t sensor,uint32_t receiver,struct route *r){
    struct media_entity_desc entity={.id=sensor};
    struct media_pad_desc pads[8];struct media_link_desc links[32];
    struct media_links_enum list={.entity=sensor,.pads=pads,.links=links};
    if(ctl(media,MEDIA_IOC_ENUM_ENTITIES,&entity)<0)return -1;
    if(entity.id!=sensor || entity.pads>8 || entity.links>32){errno=EOVERFLOW;return -1;}
    if(ctl(media,MEDIA_IOC_ENUM_LINKS,&list)<0)return -1;
    unsigned i=0;
    for(;i<entity.links;i++)if(links[i].source.entity==sensor && links[i].source.index==0 &&
                                links[i].sink.entity==receiver && links[i].sink.index==0)break;
    if(i==entity.links){errno=ENOLINK;return -1;}
    r->link=links[i];
    if(!(links[i].flags & MEDIA_LNK_FL_ENABLED)){
        links[i].flags|=MEDIA_LNK_FL_ENABLED;
        if(ctl(media,MEDIA_IOC_SETUP_LINK,&links[i])<0)return -1;
        r->changed_link=1;
    }
    r->format.which=V4L2_SUBDEV_FORMAT_ACTIVE;r->format.pad=0;
    if(ctl(rx,VIDIOC_SUBDEV_G_FMT,&r->format)<0)return -1;
    struct v4l2_subdev_format f=r->format;
    if(f.format.width==W && f.format.height==H && f.format.code==MEDIA_BUS_FMT_Y10_1X10)return 0;
    f.format.width=W;f.format.height=H;f.format.code=MEDIA_BUS_FMT_Y10_1X10;
    if(ctl(rx,VIDIOC_SUBDEV_S_FMT,&f)<0)return -1;
    r->changed_format=1;
    if(f.format.width!=W || f.format.height!=H || f.format.code!=MEDIA_BUS_FMT_Y10_1X10){errno=EINVAL;return -1;}
    return 0;
}
static int restore_route(int media,int rx,struct route *r){
    int ok=1;
    if(r->changed_format && ctl(rx,VIDIOC_SUBDEV_S_FMT,&r->format)<0){perror("restore infrared CSI receiver format");ok=0;}
    if(r->changed_link && ctl(media,MEDIA_IOC_SETUP_LINK,&r->link)<0){perror("restore infrared sensor link");ok=0;}
    return ok;
}
static int get(int fd,uint32_t id,int *out){
    struct v4l2_control c={.id=id}; if(ctl(fd,VIDIOC_G_CTRL,&c)<0)return -1;
    *out=c.value;return 0;
}
static int set(int fd,uint32_t id,int v){
    struct v4l2_control c={.id=id,.value=v}; if(ctl(fd,VIDIOC_S_CTRL,&c)<0)return -1;
    int check; if(get(fd,id,&check)<0)return -1;if(check!=v){errno=EIO;return -1;}return 0;
}
static uint64_t ms(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);
    return (uint64_t)t.tv_sec*1000+t.tv_nsec/1000000;}
static unsigned sample(const unsigned char *p,unsigned x){
    unsigned bit=(x%25)*10; p+=32*(x/25)+bit/8;return ((p[0]|(p[1]<<8))>>(bit%8))&1023;
}
#define TRY(cmd,msg) do{if((cmd)<0){perror(msg);goto cleanup;}}while(0)
#define MUST(cond,msg) do{if(!(cond)){fprintf(stderr,"%s\n",msg);goto cleanup;}}while(0)
int main(int argc,char **argv){
    if(argc!=7){fprintf(stderr,"use check.py\n");return 2;}
    struct rlimit lim={0,0};setrlimit(RLIMIT_CORE,&lim);
    struct sigaction sa={.sa_handler=interrupt};sigemptyset(&sa.sa_mask);
    sigaction(SIGINT,&sa,NULL);sigaction(SIGTERM,&sa,NULL);sigaction(SIGHUP,&sa,NULL);
    const enum v4l2_buf_type type=V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE;
    int media=-1,vid=-1,sd=-1,rx=-1,was_gain=0,was_exp=0,was_strobe=0,was_pattern=0;
    uint32_t sensor_id,receiver_id;struct route route={0};
    int active=0,bufs=0,dirty_fmt=0,dirty_ctrl=0,ok=0,restored=1;
    struct {void *p;size_t len;} maps[NB]={0};
    struct v4l2_format orig={.type=type},f={.type=type};
    struct v4l2_requestbuffers req={.type=type,.memory=V4L2_MEMORY_MMAP,.count=NB};
    enum v4l2_buf_type stream=type;
    const unsigned strobe=V4L2_CID_FLASH_STROBE_OE;
    const unsigned exposure=V4L2_CID_EXPOSURE,gain=V4L2_CID_ANALOGUE_GAIN;
    /* Match libcamera's whole-device POSIX write lock before touching either sensor. */
    struct flock owner={.l_type=F_WRLCK,.l_whence=SEEK_SET,.l_start=0,.l_len=0};
    TRY(entity_id(argv[5],&sensor_id),"invalid sensor entity id");
    TRY(entity_id(argv[6],&receiver_id),"invalid receiver entity id");
    TRY(media=open(argv[3],O_RDWR|O_CLOEXEC),"open shared CIO2 media node");
    TRY(fcntl(media,F_SETLK,&owner),"reserve shared camera controller (close camera clients first)");
    TRY(vid=open(argv[1],O_RDWR|O_NONBLOCK|O_CLOEXEC),"open CIO2");TRY(sd=open(argv[2],O_RDWR|O_CLOEXEC),"open OV7251");
    TRY(get(sd,strobe,&was_strobe),"strobe control is not available");
    MUST(was_strobe==0,"strobe already armed; refusing to disturb its owner");
    TRY(get(sd,V4L2_CID_TEST_PATTERN,&was_pattern),"get sensor test pattern");MUST(was_pattern==0,"disable synthetic test pattern first");
    TRY(get(sd,gain,&was_gain),"get gain");TRY(get(sd,exposure,&was_exp),"get exposure");
    TRY(ctl(vid,VIDIOC_G_FMT,&orig),"get CIO2 format");f=orig;
    TRY(rx=open(argv[4],O_RDWR|O_CLOEXEC),"open infrared CSI receiver");
    TRY(prepare_route(media,rx,sensor_id,receiver_id,&route),"prepare OV7251 route and CSI receiver format");
    if(f.fmt.pix_mp.width!=W||f.fmt.pix_mp.height!=H||f.fmt.pix_mp.pixelformat!=V4L2_PIX_FMT_IPU3_Y10){
        f.fmt.pix_mp.width=W;f.fmt.pix_mp.height=H;f.fmt.pix_mp.pixelformat=V4L2_PIX_FMT_IPU3_Y10;
        f.fmt.pix_mp.field=V4L2_FIELD_NONE;TRY(ctl(vid,VIDIOC_S_FMT,&f),"set CIO2 Y10");dirty_fmt=1;
    }
    unsigned stride=f.fmt.pix_mp.plane_fmt[0].bytesperline;
    MUST(f.fmt.pix_mp.width==W&&f.fmt.pix_mp.height==H&&f.fmt.pix_mp.pixelformat==V4L2_PIX_FMT_IPU3_Y10&&f.fmt.pix_mp.num_planes==1&&stride>=32*((W+24)/25),"unexpected Y10 format");
    TRY(ctl(vid,VIDIOC_REQBUFS,&req),"acquire CIO2 buffers (close camera clients first)");bufs=1;
    MUST(req.count>=2&&req.count<=NB,"incorrect CIO2 buffer count");
    for(unsigned i=0;i<req.count;i++){
        struct v4l2_plane p={0};struct v4l2_buffer b={.index=i,.type=type,.memory=V4L2_MEMORY_MMAP,.length=1,.m.planes=&p};
        TRY(ctl(vid,VIDIOC_QUERYBUF,&b),"query buffer");MUST(p.length>=stride*H,"short CIO2 buffer");
        void *v=mmap(NULL,p.length,PROT_READ|PROT_WRITE,MAP_SHARED,vid,p.m.mem_offset);
        MUST(v!=MAP_FAILED,"cannot map buffer");maps[i].p=v;maps[i].len=p.length;TRY(ctl(vid,VIDIOC_QBUF,&b),"queue");
    }
    dirty_ctrl=1;TRY(set(sd,gain,128),"set gain 128");TRY(set(sd,exposure,400),"set exposure 400");
    TRY(ctl(vid,VIDIOC_STREAMON,&stream),"start raw sensor");active=1;
    for(int phase=0;phase<3;phase++){
        MUST(!stopped,"interrupted");TRY(set(sd,strobe,phase==1),"set and read back strobe");
        uint64_t end=ms()+2400;
        for(int j=-SKIP;j<FRAMES;){
            MUST(!stopped&&ms()<end,"capture interrupted or phase timeout");
            struct pollfd pf={.fd=vid,.events=POLLIN};int pr=poll(&pf,1,140);if(pr<0&&errno==EINTR)continue;
            TRY(pr,"poll");if(!pr)continue;MUST(!(pf.revents&(POLLERR|POLLHUP|POLLNVAL)),"CIO2 poll error");
            struct v4l2_plane p={0};struct v4l2_buffer b={.type=type,.memory=V4L2_MEMORY_MMAP,.length=1,.m.planes=&p};
            int r=ctl(vid,VIDIOC_DQBUF,&b);if(r<0&&errno==EAGAIN)continue;TRY(r,"dequeue");
            MUST(b.index<req.count && !(b.flags&V4L2_BUF_FLAG_ERROR) && p.data_offset<=p.bytesused && p.bytesused<=maps[b.index].len && p.bytesused-p.data_offset>=stride*H,"invalid raw buffer");
            if(j>=0){
                struct record *row=&rows[phase][j];
                const unsigned char *raw=(const unsigned char *)maps[b.index].p+p.data_offset;
                row->seq=b.sequence;row->ts=(long long)b.timestamp.tv_sec*1000000+b.timestamp.tv_usec;
                row->timestamp_flags=b.flags&V4L2_BUF_FLAG_TIMESTAMP_MASK;
                for(unsigned y=2;y<H;y+=4)for(unsigned x=2;x<W;x+=4){
                    unsigned v=sample(raw+y*stride,x), k=(y/(H/NY))*NX+x/(W/NX);
                    row->sum[k]+=v;row->clip[k]+=v>=1019;
                }
            }
            TRY(ctl(vid,VIDIOC_QBUF,&b),"requeue");j++;
        }
        int a,e,s;TRY(get(sd,strobe,&s),"read back strobe");TRY(get(sd,gain,&a),"read back gain");TRY(get(sd,exposure,&e),"read back exposure");
        MUST(s==(phase==1)&&a==128&&e==400,"control did not retain the requested state");
    }
    ok=1;
cleanup:
    if(dirty_ctrl && set(sd,strobe,0)<0){perror("disable strobe");restored=0;}
    if(active && ctl(vid,VIDIOC_STREAMOFF,&stream)<0){perror("stop capture");restored=0;}
    if(dirty_ctrl){
        if(set(sd,exposure,was_exp)<0){perror("restore exposure");restored=0;}
        if(set(sd,gain,was_gain)<0){perror("restore gain");restored=0;}
    }
    for(unsigned i=0;i<NB;i++)if(maps[i].p)munmap(maps[i].p,maps[i].len);
    if(bufs){req.count=0;if(ctl(vid,VIDIOC_REQBUFS,&req)<0){perror("release buffers");restored=0;}}
    if(dirty_fmt && ctl(vid,VIDIOC_S_FMT,&orig)<0){perror("restore raw format");restored=0;}
    if(!restore_route(media,rx,&route))restored=0;
    if(rx>=0){close(rx);}if(sd>=0){close(sd);}if(vid>=0){close(vid);}if(media>=0){close(media);}
    if(!ok || !restored)return 2;
    printf("{\"restored\":true,\"original_exposure\":%d,\"original_gain\":%d,\"original_strobe\":%d,\"exposure_lines\":400,\"gain_register\":128,\"samples_per_tile\":400,\"tiles_x\":8,\"tiles_y\":6,\"frames\":[",was_exp,was_gain,was_strobe);
    for(int phase=0;phase<3;phase++)for(int j=0;j<FRAMES;j++){
        struct record *r=&rows[phase][j];printf("%s{\"phase\":%d,\"sequence\":%u,\"timestamp_us\":%lld,\"timestamp_flags\":%u,\"means\":[",(phase||j)?",":"",phase,r->seq,r->ts,r->timestamp_flags);
        for(unsigned k=0;k<NT;k++)printf("%s%.4f",k?",":"",r->sum[k]/400.);
        printf("],\"clipped\":[");for(unsigned k=0;k<NT;k++)printf("%s%u",k?",":"",r->clip[k]);printf("]}");
    }
    puts("]}");return 0;
}

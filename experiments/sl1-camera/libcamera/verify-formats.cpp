// SPDX-License-Identifier: CC0-1.0
// Validate the proposed stream format contract without starting a sensor stream.
#include <algorithm>
#include <iostream>
#include <libcamera/libcamera.h>
#include <libcamera/formats.h>
#include <libcamera/property_ids.h>

int main()
{
	using namespace libcamera;
	CameraManager manager;
	if (manager.start()) return 1;
	std::shared_ptr<Camera> camera;
	for (const auto &candidate : manager.cameras()) {
		if (candidate->properties().get(properties::Model) == "ov9734")
			camera = candidate;
	}
	if (!camera || camera->acquire()) return 1;
	const Size hd{ 1280, 720 };
	bool ok = true;
	for (auto role : { StreamRole::Viewfinder, StreamRole::VideoRecording, StreamRole::StillCapture }) {
		auto cfg = camera->generateConfiguration({ role });
		if (!cfg) return 1;
		auto sizes = cfg->at(0).formats().sizes(formats::NV12);
		std::cout << role << ":";
		if (cfg->at(0).size != hd ||
		    std::count(sizes.begin(), sizes.end(), hd) != 1 ||
		    std::count(sizes.begin(), sizes.end(), Size(1280, 704)) != 1)
			ok = false;
		for (const Size &size : sizes) {
			cfg->at(0).size = size;
			if (cfg->validate() == CameraConfiguration::Invalid || cfg->at(0).size != size) {
				std::cout << " INVALID";
				ok = false;
			}
			std::cout << " " << size;
		}
		std::cout << "\n";
	}
	for (auto role : { StreamRole::Raw, StreamRole::VideoRecording }) {
		auto cfg = camera->generateConfiguration({ StreamRole::Viewfinder, role });
		if (!cfg) return 1;
		cfg->at(0).size = hd;
		if (cfg->validate() == CameraConfiguration::Invalid || cfg->at(0).size == hd)
			ok = false;
		std::cout << "Viewfinder plus " << role << " effective size: " << cfg->at(0).size << "\n";
	}
	camera->release();
	return ok ? 0 : 1;
}

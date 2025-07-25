//go:build windows

package ble

/*
#cgo CXXFLAGS: -std=c++20 -DWINRT_LEAN_AND_MEAN -DWIN32_LEAN_AND_MEAN -I./generated_headers -IC:/PROGRA~2/WINDOW~1/10/Include/10.0.26100.0/um -IC:/PROGRA~2/WINDOW~1/10/Include/10.0.26100.0/shared
#cgo LDFLAGS: -lwindowsapp -LC:/PROGRA~2/WINDOW~1/10/Lib/10.0.26100.0/um/x64
#cgo CFLAGS: -DUNICODE -D_UNICODE
#include <stdlib.h>
#include "BLEBridge_windows.h"
*/
import "C"

import "unsafe"

func startBLE(clientID, deviceID string) error {
	cClient := C.CString(clientID)
	defer C.free(unsafe.Pointer(cClient))
	cDev := C.CString(deviceID)
	defer C.free(unsafe.Pointer(cDev))

	C.BLEBridgeStart(cClient, cDev)
	return nil
}

func stopBLE() error {
	C.BLEBridgeStop()
	return nil
}

func publishBLE(payload []byte) error {
	if len(payload) == 0 {
		return nil
	}
	cData := C.CBytes(payload)
	defer C.free(cData)

	C.BLEBridgeSend(cData, C.int(len(payload)))
	return nil
}

//export GoOnBLEMessage
func GoOnBLEMessage(deviceID *C.char, data unsafe.Pointer, length C.int) {
	id := C.GoString(deviceID)
	body := C.GoBytes(unsafe.Pointer(data), length)
	onMessage(id, body)
}

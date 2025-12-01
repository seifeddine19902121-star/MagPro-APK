[app]
title = MagPro
package.name = MagPro
package.domain = org.magpro
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json
version = 7.1.0
requirements = python3,kivy,kivymd,websocket-client,requests,urllib3,pillow
icon.filename = apk_icon.png
orientation = portrait
fullscreen = 0
android.permissions = INTERNET, ACCESS_NETWORK_STATE, WRITE_EXTERNAL_STORAGE, READ_EXTERNAL_STORAGE
android.api = 33
android.minapi = 21
android.accept_sdk_license = True
android.skip_update = False
android.logcat_filters = *:S python:D
android.archs = arm64-v8a
android.allow_backup = True
android.debug_artifact = apk
android.uses_cleartext_traffic = 1

[buildozer]
log_level = 2
warn_on_root = 1

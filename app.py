import binascii
import hashlib
import machine
import network
import ntptime
import os
import usocket
import time

import settings

_MAX_ERROR_COUNT = const(5)

_WIFI_CONNECT_TIMEOUT = const(15)

_WLAN = network.WLAN(network.STA_IF)

_PIN_ID_LED = const("LED")
_PIN_ID_LED_BINARY = const(b'led')
_PIN_ID_MIN = const(0)
_PIN_ID_MAX = const(22)

_HTTP_PORT = const(80)
_HTTP_BUFFER_SIZE = const(1024)
_HTTP_NEWLINE = const(b'\r\n')
_HTTP_NO_CONTENT = const(b'HTTP/1.1 204 No Content\r\nContent-Length: 0\r\n\r\n')
_HTTP_RESPONSE_1 = const("HTTP/1.1 200 OK\r\nContent-Length: ")
_HTTP_RESPONSE_2 = const("\r\nContent-Type: text/plain\r\n\r\n")
_HTTP_ERROR_1 = const("HTTP/1.1 422 Unprocessable Content\r\nContent-Length: ")
_HTTP_ERROR_2 = const("\r\nContent-Type: text/plain\r\n\r\n")

_HTTP_POST_METHOD = const(b'post ')
_HTTP_POST_METHOD_STR = const('post')
_HTTP_GET_METHOD = const(b'get ')
_HTTP_GET_METHOD_STR = const('get')
_HTTP_VERSION = const(b' http')
_HTTP_ALLOWED_URI = const(b'/pins')
_HTTP_HEADER_PIN = const(b'x-pin: ')
_HTTP_HEADER_STATE = const(b'x-state: ')
_HTTP_HEADER_TIME = const(b'x-time: ')
_HTTP_HEADER_HASH = const(b'x-hash: ')
_HTTP_HEADER_KEY = const(b'x-key: ')

_STATE_ON = const(b'on')
_STATE_ON_STR = const('on')
_STATE_OFF_STR = const('off')

_IP_NONE = const('0.0.0.0')

_CONFIG_DIR = const('/pins')

def IsConnectedToWiFi():
    if _WLAN.isconnected():
        config = _WLAN.ifconfig()
        PrintDebug("ifconfig: ", config)
        if config[0] == _IP_NONE:
            return False
        return True
        
    return False

def ConnectToWifi():
    if IsConnectedToWiFi():
        return
    
    _WLAN.active(True)
    
    PrintDebug("Connecting to WiFi...")
        
    _WLAN.connect(settings.WIFI_SSID, settings.WIFI_PASS)
    
    count = 0
    while not _WLAN.isconnected():
        if count >= _WIFI_CONNECT_TIMEOUT:
            raise Exception("WIFI Failed to connect")
        count += 1
        time.sleep(1)
    
    PrintDebug("WiFi connected")
    PrintDebug("IP Info: ", _WLAN.ifconfig())

def CreateSocket():
    s = usocket.socket()
    s.setsockopt(usocket.SOL_SOCKET, usocket.SO_REUSEADDR, 1)
    s.bind(usocket.getaddrinfo(_IP_NONE, _HTTP_PORT)[0][-1])
    s.listen()
    return s

def GetCurrentPinState(pinId):
    pin = machine.Pin(pinId, machine.Pin.OUT)
    
    if pin.value() == 1:
        return _STATE_ON_STR
    return _STATE_OFF_STR

def GetHeader(headerId, request):
    start = request.find(headerId)
    if start < 0:
        return None
    
    end = request.find(_HTTP_NEWLINE, start + len(headerId))
    value = request[start + len(headerId):end]
    PrintDebug(headerId.decode(), value)
    return value

def GetMethod(request):
    start = request.find(_HTTP_POST_METHOD)
    if start == 0:
        return _HTTP_POST_METHOD_STR

    start = request.find(_HTTP_GET_METHOD)
    if start == 0:
        return _HTTP_GET_METHOD_STR

    return None

def GetPin(request, sha256):
    pinId = GetHeader(_HTTP_HEADER_PIN, request)
    if pinId is None:
        return None

    sha256.update(pinId)
    
    if pinId == _PIN_ID_LED_BINARY:
        pinId = _PIN_ID_LED
    elif pinId.isdigit():
        pinId = int(pinId)
        if pinId < _PIN_ID_MIN or pinId > _PIN_ID_MAX:
            return None
    else:
        return None
    
    return pinId

def GetPinState(request, sha256):
    pinState = GetHeader(_HTTP_HEADER_STATE, request)
    if pinState is None:
        return None

    sha256.update(pinState)
    
    return pinState
    
def PrintDebug(message, obj=None):
    if settings.DEBUG:
        if obj is None:
            print("[DEBUG " + str(time.time_ns()) + "] " + message)
        else:
            print("[DEBUG " + str(time.time_ns()) + "] " + message, obj)

def RespondError(con, message):
    PrintDebug(message)

    con.send(_HTTP_ERROR_1 + str(len(message)) + _HTTP_ERROR_2 + message)
    con.close()

def RespondContent(con, message):
    con.send(_HTTP_RESPONSE_1 + str(len(message)) + _HTTP_RESPONSE_2 + message)
    con.close()
    
def RespondNoContent(con):
    con.send(_HTTP_NO_CONTENT)
    con.close()

def SetPin(pinId, state):
    pin = machine.Pin(pinId, machine.Pin.OUT)
    if state == _STATE_ON:
        pin.on()

        if settings.RESTORE_ON_BOOT:
            p = open(_CONFIG_DIR + "/" + str(pinId), "wb")
            p.write(state)
            p.close()
    else:
        pin.off()
    
        if settings.RESTORE_ON_BOOT and str(pinId) in os.listdir(_CONFIG_DIR):
            os.remove(_CONFIG_DIR + "/" + str(pinId))
    
def ValidateEndPoint(request):
    method = GetMethod(request)
    if method != _HTTP_POST_METHOD_STR and method != _HTTP_GET_METHOD_STR:
        return False
    
    start=len(method) + 1
    end = request.find(_HTTP_VERSION, start)
    httpRequest = request[start:end]
    PrintDebug("URI: ", httpRequest)
    
    if httpRequest != _HTTP_ALLOWED_URI:
        return False
    
    return True
            
def ValidateHash(request, sha256):
    requestHash = GetHeader(_HTTP_HEADER_HASH, request)
    if requestHash is None:
        return False
    
    keyId = GetHeader(_HTTP_HEADER_KEY, request)
    if keyId is None:
        keyId = 0
    elif keyId.isdigit():
        keyId = int(keyId)
    else:
        return False
    
    if keyId >= len(settings.SHARED_SECRETS):
        return False
    
    sha256.update(settings.SHARED_SECRETS[keyId])
    computedHash = binascii.hexlify(sha256.digest()).lower()
    PrintDebug("Computed Hash: ", computedHash)
    
    if requestHash != computedHash:
        return False
    
    return True

def ValidateRequestTime(request, sha256):
    requestTime = GetHeader(_HTTP_HEADER_TIME, request)
    if requestTime is None:
        return False
    
    sha256.update(requestTime)
    
    if requestTime.isdigit():
        requestTime = int(requestTime)
    else:
        return False
        
    ntptime.settime()
    PrintDebug("System Time: ", time.time())
    if time.time() - requestTime > settings.MAX_TTL:
        return False
    
    return True

def RestoreConfig():
    if not settings.RESTORE_ON_BOOT:
        return
    
    PrintDebug("Restoring Last Known Config")
    if not "pins" in os.listdir("/"):
        os.mkdir(_CONFIG_DIR)
    pins = os.listdir(_CONFIG_DIR)
    for pin in pins:
        PrintDebug("Configuring " + pin)
        p = open(_CONFIG_DIR + "/" + pin, "rb")
        state = p.read()
        p.close()
        PrintDebug("Initalizing " + pin + " to " + state.decode())
        if pin.isdigit():
          pin = int(pin)
        SetPin(pin, state)
        
def Main():
    RestoreConfig()
    
    PrintDebug("Starting Server")
    
    s = CreateSocket()
    s.settimeout(settings.WIFI_RECONNECT_INTERVAL)
    
    while True:
        try:
            ConnectToWifi()
            
            PrintDebug("Waiting for client")
            con, addr = s.accept()
            PrintDebug("Client connected from", addr)
            
            # Receive Data
            request = con.recv(_HTTP_BUFFER_SIZE).lower()
            PrintDebug("Received: ", request)
            
            # Check request method and URI
            if not ValidateEndPoint(request):
                RespondError(con, "Invalid URI and/or method")
                continue
            
            method = GetMethod(request)
            
            # Create SHA-256 object for use as we add data
            sha256 = hashlib.sha256()
            
            # X-Pin header
            pinId = GetPin(request, sha256)
            if pinId is None:
                RespondError(con, "Invalid X-Pin header, ignoring request")
                continue

            if method == _HTTP_POST_METHOD_STR:
                # X-State header
                pinState = GetPinState(request, sha256)
                if pinState is None:
                    RespondError(con, "Invalid X-State header, ignoring request")
                    continue
              
            # X-Time Header
            if not ValidateRequestTime(request, sha256):
                RespondError(con, "Invalid X-Time header, ignoring request")
                continue
                        
            # X-Hash header
            if not ValidateHash(request, sha256):
                RespondError(con, "Invalid X-Hash header, ignoring request")
                continue
            
            # All good, process request
            if method == _HTTP_POST_METHOD_STR:
                SetPin(pinId, pinState)
                
                # Respond to client
                RespondNoContent(con)
            else:
                value = GetCurrentPinState(pinId)
                PrintDebug("Current Pin Value: ", value)
                
                # Respond to client
                RespondContent(con, value)
            
        except OSError as ex:
            if con is not None:
                con.close()

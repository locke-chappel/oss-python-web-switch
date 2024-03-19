web-switch
==
This is a simple HTTP "REST" API for toggling GPIO high/low states on an RPi Pico W.

What can it be used for? Really anything that you want a RESTful-like API for toggling GPIO pins. I've used it for controlling LED lighting in a room and emulating Wake-on-LAN for Single Board Computers (additional circuitry may be required depending on your fault tolerance/reboot/crash behavior needs - remember the pin will be low while the RPi Pico reboots for any reason).

## Install/Setup
Copy `main.py`, `settings.py`, and `app.py` _or_ `app.mpy` to the root of your RPi Pico W. Next, edit `settings.py` on the RPi Pic W with your settings.

_If using mpy files make sure use a compatible version of myp-cross for the version of Micropython you installed on your RPi Pico W_

## API
HTTP POST to `/pins` with the following headers: `X-Pin: <pin number>`, `X-State: <on|off>`, `X-Time: <seconds since unix epoch>`, and `X-Hash: <sha-256>` sets the pin's state to specified value.  

HTTP GET to `/pins` with the following headers: `X-Pin: <pin number>`, `X-Time: <seconds since unix epoch>`, and `X-Hash: <sha-256>` gets the pin's current state.  

An optional header of `X-Key: <key index>` can be specified to select a specific shared secret. If not provided the first secret will be assumed.  

#### Valid Pin Numbers
0-22 inclusive and `LED`

#### Hash Value
The hash value is the SHA-256 hash of `<pin number><state><time><shared secret>`. Omit the `<state>` value if making a GET request.

#### Responses
On successful POST request `HTTP 204 No Content` will be returned.  

On successful GET request `HTTP 200 OK` will be returned with a body containing either `on` or `off`.  

On error `HTTP 422 Unprocessable Content` with plain text error message will be returned.  

## Settings
The `settings.py` file contains configurable values that you will need to set (e.g. your WiFi settings and the shared secret). It contains a couple of other optional settings that can assist with debugging and tuning.

`DEBUG` if `True` then debugging info will printed to the console  
  
`WIFI_SSID` your WiFi SSID  
  
`WIFI_PASS` your WiFi password  
  
`WIFI_RECONNECT_INTERVAL` the number of seconds before the program will test if the WiFi connection is still alive and if not reconnect (default is 5 minutes)  
  
`SHARED_SECRET` an array of pre-shared shared secrets to used when generating the hash header value  
  
`MAX_TTL` the number of seconds old a request be before it is rejected  
  
`RESTORE_ON_BOOT` if `True` then pin settings will be saved to flash and reloaded upon controller boot  


## Example Client Script
You may run this script interactively or you can specify get/set as the first argument, the pin ID as the second argument, and if setting the state as the third argument to avoid being prompted.
_awk, BASH, date, and sha256sum are required._

```bash
#!/bin/bash

host='http://<pico-w dns or ip>/pins'
secret='<my shared secret goes here>'

function prompt() {
  local ok=false
  local response
  while ! $ok
  do
    read -p "$1" response
      if [[ -z "$response" && ! -z "$2" ]]; then
        response="$2"
      fi
      
      if [[ ! -z "$response" ]]; then
        ok=true
      fi
  done
  echo "$response"
}

if [[ ! -z "$1" ]]; then
  get="$1"
else
  get=$(prompt "Get or Set? [Set] ")
fi

if [[ -z "$get" || "${get,,}" != "get" ]]; then
  get=false
else
  get=true
fi
  
if [[ ! -z "$2" ]]; then
  pin="$2"
else
  pin=$(prompt "Pin ID (0-22, LED): ")
fi

if [[ "$get" != "true" ]]; then
  if [[ ! -z "$3" ]]; then
    state="$3"
  else
    state=$(prompt "State (on|off): ")
  fi

  if [[ "${state,,}" != "on" ]]; then
    state="off"
  fi
else
  state=  
fi

now=$(date +%s)

hash=$(echo -n "${pin,,}${state,,}${now}${secret}" | sha256sum | awk '{ print $1 }')

if [[ "$get" = "true" ]]; then
  curl \
    -X GET \
    -H 'User-Agent:' \
    -H 'Accept:' \
    -H 'Host:' \
    -H "X-Pin: ${pin,,}" \
    -H "X-Time: $now" \
    -H "X-Hash: $hash" \
    "$host"
else
  curl \
    -X POST \
    -H 'User-Agent:' \
    -H 'Accept:' \
    -H 'Host:' \
    -H "X-Pin: ${pin,,}" \
    -H "X-State: ${state,,}" \
    -H "X-Time: $now" \
    -H "X-Hash: $hash" \
    "$host"  
fi
```

The above script is just an example, any HTTP client that can set custom headers can be used including other more complex programs. The most difficult parts will be ensuring compatible time zone configurations for computing the timestamp value and ensuing all data is lowercase prior to hashing (the API will lowercase the request internally but if you computed the hash value using capital letters then it will be wrong, this does _not_ apply to the shared secret - it must match exactly on both sides).

#### Example Invocations
`$ ./script` will then prompt you for each input value as needed.  

`$ ./script get led` will return the status of the LED "pin", either `on` or `off` will be written to standard out as applicable.  

`$ ./script set 5 on` will turn GPIO 5 on

## Security
While some consideration was made towards security, in the end this is running on a microcontroller with very little resources so for example TLS is not supported. Without TLS many authentication/authorization designs don't make sense either.

To that end a shared secret HMAC design with a temporal component was added to limit replay attacks and provide some level of verification of origin (an attacker can't create new requests or edit existing ones without obtaining the shared secret and intercepted messages can only be reused for a few seconds).

Is this OK? That depends on your needs. In a home lab (like where I am using this) it's fine - I probably could have ignored security entirely and been OK. This project was never meant for use in a commercial/enterprise context, let alone one with strict security compliance needs.

_**Use at your own risk.**_

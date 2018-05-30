# RaspberryPi config service via Bluetooth (ble2wifi)

Setup Raspberry Pi WiFi access via Bluetooth (in development)

## Requeriments

### Bluetooth managment settings

current requeriments settings: `powered connectable bondable le advertising secure-conn`

### Setup commands (provisional)

works with next secuence on `btmgmt`:

```bash
power off
bredr off
power on
le on
advertising on
connectable on
bondable on
``` 

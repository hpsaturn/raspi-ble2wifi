#!/usr/bin/env python3

import dbus
import dbus.exceptions
import dbus.mainloop.glib
import dbus.service

import array

try:
  from gi.repository import GObject
except ImportError:
  import gobject as GObject

import sys
from gatt import *
from wifi import Cell, Scheme

mainloop = None

class Application(dbus.service.Object):
    """
    org.bluez.GattApplication1 interface implementation
    """
    def __init__(self, bus):
        self.path = '/'
        self.services = []
        dbus.service.Object.__init__(self, bus, self.path)
        self.add_service(WifiConfigService(bus, 0))

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_service(self, service):
        self.services.append(service)

    @dbus.service.method(DBUS_OM_IFACE, out_signature='a{oa{sa{sv}}}')
    def GetManagedObjects(self):
        response = {}
        print('GetManagedObjects')

        for service in self.services:
            response[service.get_path()] = service.get_properties()
            chrcs = service.get_characteristics()
            for chrc in chrcs:
                response[chrc.get_path()] = chrc.get_properties()
                descs = chrc.get_descriptors()
                for desc in descs:
                    response[desc.get_path()] = desc.get_properties()

        return response


class WifiConfigService(Service):
    """
    Wifi Config service that provides characteristics and descriptors for
    raspbian wifi config.

    """
    WIFI_SVC_UUID = '181c5678-1234-5678-1234-56789abcdef0'

    def __init__(self, bus, index):
        Service.__init__(self, bus, index, self.WIFI_SVC_UUID, True)
        self.add_characteristic(WifiSecureCharacteristic(bus, 0, self))


class CharacteristicUserDescriptionDescriptor(Descriptor):
    """
    Writable CUD descriptor.

    """
    CUD_UUID = '181c'

    def __init__(self, bus, index, characteristic):
        self.writable = 'writable-auxiliaries' in characteristic.flags
        self.value = array.array('B', b'Raspi BLE2WiFi https://github.com/hpsaturn/raspi-ble2wifi')
        self.value = self.value.tolist()
        Descriptor.__init__(
                self, bus, index,
                self.CUD_UUID,
                ['read', 'write'],
                characteristic)

    def ReadValue(self, options):
        print('Read CharacteristicUserDescriptionDescriptor')
        return self.value

    def WriteValue(self, value, options):
        if not self.writable:
            raise NotPermittedException()
        self.value = value


class WifiSecureCharacteristic(Characteristic):
    """
    Wifi characteristic requiring secure connection.

    """
    WIFI_CHRC_UUID = '181c5678-1234-5678-1234-56789abcdef5'

    def __init__(self, bus, index, service):
        Characteristic.__init__(
                self, bus, index,
                self.WIFI_CHRC_UUID,
                ['secure-read', 'secure-write'],
                service)
        self.value = []
        self.add_descriptor(WifiSecureDescriptor(bus, 2, self))
        self.add_descriptor(CharacteristicUserDescriptionDescriptor(bus, 3, self))

    def ReadValue(self, options):
        print('WifiSecureCharacteristic Read: ' + repr(self.value))
        return self.value

    def WriteValue(self, value, options):
        print('WifiSecureCharacteristic Write: ' + repr(value))
        self.value = value


class WifiSecureDescriptor(Descriptor):
    """
    Wifi descriptor requiring secure connection. Returns a static value.

    """
    WIFI_DESC_UUID = '181c5678-1234-5678-1234-56789abcdef6'

    def __init__(self, bus, index, characteristic):
        Descriptor.__init__(
                self, bus, index,
                self.WIFI_DESC_UUID,
                ['secure-read', 'secure-write'],
                characteristic)
        self.value = []

    def ReadValue(self, options):
        print('WifiSecureCharacteristic Read: ' + repr(self.value))
        return self.value

    def WriteValue(self, value, options):
        print('WifiSecureCharacteristic Write: ' + repr(value))
        self.value = value

class WifiScanningService(Service):
    """
    Scanning ssid near to raspberryPi
    """
    HR_UUID = '0000180d-0000-1000-8000-00805f9b34fb'

    def __init__(self, bus, index):
        Service.__init__(self, bus, index, self.HR_UUID, True)
        self.add_characteristic(WifiScanningChrc(bus, 0, self))
        self.add_characteristic(BodySensorLocationChrc(bus, 1, self))
        self.add_characteristic(HeartRateControlPointChrc(bus, 2, self))
        self.energy_expended = 0

class WifiScanningChrc(Characteristic):
    HR_MSRMT_UUID = '00002a37-0000-1000-8000-00805f9b34fb'

    def __init__(self, bus, index, service):
        Characteristic.__init__(
                self, bus, index,
                self.HR_MSRMT_UUID,
                ['notify'],
                service)
        self.notifying = False
        self.hr_ee_count = 0

    def hr_msrmt_cb(self):
        value = []
        value.append(dbus.Byte(0x06))

        value.append(dbus.Byte(randint(90, 130)))

        if self.hr_ee_count % 10 == 0:
            value[0] = dbus.Byte(value[0] | 0x08)
            value.append(dbus.Byte(self.service.energy_expended & 0xff))
            value.append(dbus.Byte((self.service.energy_expended >> 8) & 0xff))

        self.service.energy_expended = \
                min(0xffff, self.service.energy_expended + 1)
        self.hr_ee_count += 1

        print('Updating value: ' + repr(value))

        self.PropertiesChanged(GATT_CHRC_IFACE, { 'Value': value }, [])

        return self.notifying

    def _update_hr_msrmt_simulation(self):
        print('Update HR Measurement Simulation')

        if not self.notifying:
            return

        GObject.timeout_add(1000, self.hr_msrmt_cb)

    def StartNotify(self):
        if self.notifying:
            print('Already notifying, nothing to do')
            return

        self.notifying = True
        self._update_hr_msrmt_simulation()

    def StopNotify(self):
        if not self.notifying:
            print('Not notifying, nothing to do')
            return

        self.notifying = False
        self._update_hr_msrmt_simulation()


def register_app_cb():
    print('GATT application registered')


def register_app_error_cb(error):
    print('Failed to register application: ' + str(error))
    mainloop.quit()


def find_adapter(bus):
    remote_om = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, '/'),
                               DBUS_OM_IFACE)
    objects = remote_om.GetManagedObjects()

    for o, props in objects.items():
        if GATT_MANAGER_IFACE in props.keys():
            return o

    return None

def wifi_scan_ssids(device):
    ssids = [cell.ssid for cell in Cell.all(device)]
    print (ssids)


def main():
    global mainloop

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

    bus = dbus.SystemBus()

    adapter = find_adapter(bus)
    if not adapter:
        print('GattManager1 interface not found')
        return

    service_manager = dbus.Interface(
            bus.get_object(BLUEZ_SERVICE_NAME, adapter),
            GATT_MANAGER_IFACE)

    app = Application(bus)

    mainloop = GObject.MainLoop()

    wifi_scan_ssids('wlan0')

    print('Registering GATT application...')

    service_manager.RegisterApplication(app.get_path(), {},
                                    reply_handler=register_app_cb,
                                    error_handler=register_app_error_cb)

    mainloop.run()

if __name__ == '__main__':
    main()

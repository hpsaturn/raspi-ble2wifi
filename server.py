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

    print('Registering GATT application...')

    service_manager.RegisterApplication(app.get_path(), {},
                                    reply_handler=register_app_cb,
                                    error_handler=register_app_error_cb)

    mainloop.run()

if __name__ == '__main__':
    main()

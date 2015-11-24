#!/usr/bin/env python2

import io
import os
import re
import sys
import time
import fcntl
import socket
import random
import struct
import argparse
from subprocess import Popen, PIPE, STDOUT

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
    '''
	Create the arguments
    '''
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--interface", help="Select the interface to use")
    return parser.parse_args()

def iwconfig():
    monitors = []
    wifi_intfs = []

    try:
        proc = Popen(['/sbin/iwconfig'], stdout=PIPE, stderr=DN)
    except OSError:
        sys.exit('['+R+'-'+W+'] Could not execute "iwconfig"')

    for line in proc.communicate()[0].split('\n'):
        if len(line) == 0: continue # Isn't an empty string
        if line[0] != ' ': # Doesn't start with space
            iface = line[:line.find(' ')] # is the interface
            if 'Mode:Monitor' in line:
                monitors.append(iface)
            elif 'IEEE 802.11' in line:
                wifi_intfs.append(iface)

    return monitors, wifi_intfs

def get_mon_iface(args):
    '''
    Get the monitor mode interface name
    '''
    # Kill any potentialy interfering programs
    monitors, wifi_intfs = iwconfig()

    if args.interface:
        iface = args.interface
    else:
        if len(monitors) > 0:
            # Just use the first monitor mode interface
            iface = monitors[0]
        else:
            iface = get_iface(wifi_intfs)

    orig_mac = get_mac(iface)
    print '[*] Original MAC address: %s' % orig_mac
    #Changes MAC and brings it up in monitor mode
    new_mac = rand_mac(iface)
    print '[*] New MAC address: %s' % new_mac

    return orig_mac, iface

def get_mac(interface):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    info = fcntl.ioctl(s.fileno(), 0x8927,  struct.pack('256s', interface[:15]))
    return ':'.join(['%02x' % ord(char) for char in info[18:24]])

def rand_mac(interface):
    '''
    https://www.centos.org/docs/5/html/5.2/Virtualization/
    sect-Virtualization-Tips_and_tricks-Generating_a_new_unique_MAC_address.html
    '''
    os.system('/sbin/ip link set %s down' % interface)
    mac = [ 0x00, 0x16, 0x3e,
            random.randint(0x00, 0x7f),
            random.randint(0x00, 0xff),
            random.randint(0x00, 0xff) ]
    mac = ':'.join(map(lambda x: "%02x" % x, mac))

    os.system('/sbin/ip link set dev {} address {}'.format(interface, mac))
    os.system('/sbin/iwconfig %s mode monitor' % interface)
    os.system('/sbin/ip link set %s up' % interface)

    return mac

def get_iface(wifi_intfs):
    '''
    Get the interface we're going to interact with
    '''
    if len(wifi_intfs) < 1:
        sys.exit('['+R+'-'+W+'] No wireless interfaces found, bring one up and try again')

    if len(wifi_intfs) == 1:
        return interface[0]

    return get_best_intf(wifi_intfs)

def get_best_intf(wifi_intfs):
    '''
    Run iwlist and select wifi interface that returns most APs
    '''
    scanned_aps = []

    for iface in wifi_intfs:
        count = iface_scan(iface)
        if count == 0:
            print '['+G+'+'+W+'] Networks discovered by '+G+iface+W+': '+T+str(count)+W
            print '['+R+'-'+W+'] Rescanning '+G+iface+W
            count = iface_scan(iface)
        scanned_aps.append((count, iface))
        print '['+G+'+'+W+'] Networks discovered by '+G+iface+W+': '+T+str(count)+W

    # Returns the interface that found the most APs
    return max(scanned_aps)[1]

def iface_scan(iface):
    count = 0
    proc = Popen(['/sbin/iwlist', iface, 'scan'], stdout=PIPE, stderr=DN)
    for line in proc.communicate()[0].split('\n'):
        if ' - Address:' in line: # first line in iwlist scan for a new AP
           count += 1
    return count

def select_target(mon_iface):
    '''
    Get wash output
    '''
    output = []
    filename = 'wash.log'
    try:
        with io.open(filename, 'wb') as writer, io.open(filename, 'rb', 1) as reader:
            cmd = 'wash -i {} -C'.format(mon_iface)
            print '[*] Running `{}`'.format(cmd)
            time.sleep(3)
            proc = Popen(cmd.split(), stdout=writer)
            # wash never stops
            while proc.poll() is None:
                output += reader.readlines()
                targets = print_targets(output)
                time.sleep(.25)
    except KeyboardInterrupt:
        choice = raw_input('[*] Enter the number of your choice: ')
        return output, targets[choice]

def print_targets(output):
    '''
    Print the targets and return them in a dict
    '''
    os.system('clear')
    print '[*] Targets:\n'
    targets = get_targets(output)
    for idx in targets:
        mac, chan, locked, essid = targets[idx]
        print '[{}] {} {} {}'.format(idx, mac, essid, locked)
    print '\n[*] Hit Ctrl-C to make a selection'

    return targets

def get_targets(out):
    '''
    Parse wash output for target macs and essids
    '''
    targets = {}
    counter = 0
    for line in out:
        if line.count(':') == 5:
            counter += 1
            line = line.split()
            # For some reason sometimes 1 AP around me throws tons of \x00's in
            # the mac
            mac = line[0].replace('\x00', '')
            chan = line[1]
            locked = line[4]
            essid = line[5]

            if 'yes' in locked.lower():
                locked = 'Locked'
            else:
                locked = ''

            targets[str(counter)] = (mac, chan, locked, essid)

    return targets

def run_reaver(targets, mon_iface):
    for t in targets:
        essid, chan, mac = t
        cmd = 'reaver -i {} -c {} -b {} -vv -S'.format(mon_iface, chan, mac)

def cleanup(orig_mac, mon_iface):
    '''
    Removes monitor mode, changes MAC back, restarts network-manager,
    removes wash.log, and prints a closing message
    '''
    os.system('ifconfig %s down' % mon_iface)
    os.system('/sbin/ip link set dev {} address {}'.format(mon_iface, orig_mac))
    os.system('iwconfig %s mode managed' % mon_iface)
    os.system('ifconfig %s up' % mon_iface)
    os.system('service network-manager restart')
    os.system('rm wash.log')
    sys.exit('\n['+R+'!'+W+'] Closing...')

def main():
    args = parse_args()
    orig_mac, mon_iface = get_mon_iface(args)
    out, target = select_target(mon_iface)
    mac, chan, locked, essid = target
    print 'You chose:', mac, chan, locked, essid
    cleanup(orig_mac, mon_iface)

main()

#!/usr/bin/env python3

###########################################################
#
# scripts/checkcves.py - Online CVE Database Interface.
#
# Copyright (C) 2019 Timesys Corporation
#
#
# This source is released under the MIT License.
#
###########################################################

import argparse
import os
import sys
import json
from distutils import spawn

from lib import llapi

NVD_BASE_URL = 'https://nvd.nist.gov/vuln/detail/'
API_DOC = '%s/docs/wiki/engineering/LinuxLink_Key_File' % llapi.LinuxLinkURL
INFO_PAGE = 'https://www.timesys.com/security/vulnerability-patch-notification/'

bogus_whitelist = "CVE-1234-1234"

def get_usage():
    return('This script sends a json manifest file for an image to LinuxLink '
           'to check the CVE status of the recipes. You may specify a manifest '
           'file, or generate one from a given image name.  If no image or '
           'manifest is specified, you will be prompted to select an image.\n\n'
           'Subscribing to notifications requires a LinuxLink API keyfile, and '
           'an active LinuxLink subscription.\n\n'
           'See this document for keyfile information:\n'
           '%s\n\n'
           % API_DOC)


def print_demo_notice(bad_key=False):
    print('\n-- Vigiles Demo Mode Notice --', file=sys.stderr)

    if bad_key:
         print('\tNo API keyfile was found, or the contents were invalid.\n\n'
              '\tPlease see this document for API key information:\n'
              '\t%s\n' % API_DOC,
              file=sys.stderr)
    else:
        print('\tNo active subscription for this account.\n', file=sys.stderr)

    print('\tThe script will continue in demo mode, which will link you to '
            'temporarily available online results only.\n'
          '\tYou will need to login or register for a free account in order to '
            'see the report.\n', 
          file=sys.stderr)
    print('\tFor more information on the security notification service, '
            'please visit:\n'
          '\t%s\n' % INFO_PAGE,
          file=sys.stderr)


def handle_cmdline_args():
    parser = argparse.ArgumentParser(description=get_usage())
    parser.add_argument('-s', '--subscribe',
                        help='Subscribe to weekly email reports for this manifest',
                        action='store_true',
                        default=False,
                        dest='subscribe')
    parser.add_argument('-o', '--outfile',
                        help='Print results to FILE instead of STDOUT',
                        metavar='FILE')
    parser.add_argument('-k', '--kconfig',
                        help='Kernel .config (not defconfig) to submit for CVE filtering',
                        metavar='FILE',
                        dest='kconfig')
    parser.add_argument('-u', '--uboot-config',
                        help='U-Boot .config (not defconfig) to submit for CVE filtering',
                        metavar='FILE',
                        dest='uboot_config')

    parser.add_argument('-K', '--keyfile', dest='llkey',
                        help='Location of LinuxLink credentials file')
    parser.add_argument('-C', '--dashboard-config', dest='lldashboard',
                        help='Location of LinuxLink Dashboard Config file')
    parser.add_argument('-F', '--subfolder-name', dest='subfolder_name',
                        help='Name of subfolder to upload to')

    parser.add_argument('-U', '--upload-only', dest='upload_only',
                        help='Upload the manifest only; do not wait for report.',
                        action='store_true', default=False)
    parser.add_argument('-m', '--manifest', required=True,
                        help='Pre-generated JSON image manifest file to check',
                        metavar='FILE')
    return parser.parse_args()


def read_manifest(manifest_file):
    try:
        with open(manifest_file, 'r') as f:
            manifest_data = ''.join(line.rstrip() for line in f)
    except (OSError, IOError, UnicodeDecodeError) as e:
        print('Error: Could not open manifest: %s' % e)
        sys.exit(1)
    return manifest_data


def print_cves(result, outfile=None):
    cves = result.get('cves', {})
    if cves:
        print('\n\n-- Recipe CVEs --', file=outfile)
        for pkg, info in cves.items():
            for cve in info:
                print('\n\tRecipe:  %s' % pkg, file=outfile)
                print('\tVersion: %s' % cve['version'], file=outfile)
                print('\tCVE ID:  %s' % cve['cve_id'], file=outfile)
                print('\tURL:     %s%s' % (NVD_BASE_URL, cve['cve_id']), file=outfile)
                print('\tCVSSv3:  %s' % cve['cvss'], file=outfile)
                print('\tVector:  %s' % cve['vector'], file=outfile)
                print('\tStatus:  %s' % cve['status'], file=outfile)
                patches = cve.get('fixedby')
                if patches:
                    if cve['status'] == 'Unfixed, Patch Available':
                        print('\tPatched in meta-timesys-security commit(s):',
                              file=outfile)
                    else:
                        print('\tPatched by:', file=outfile)
                    for patch in patches:
                        print('\t* %s' % patch, file=outfile)


def parse_cve_counts(counts, category):
    total = counts.get(category, 0)
    kernel = counts.get('kernel', {}).get(category, 0)
    toolchain = counts.get('toolchain', {}).get(category, 0)
    rfs = total - kernel - toolchain
    return {'total': total,
            'rfs': rfs,
            'kernel': kernel,
            'toolchain': toolchain}


def parse_cvss_counts(counts, severity):
    c = counts.get(severity)
    if c is None:
        return 0
    return c.get('unfixed', 0) + c.get('fixed', 0)


def print_report_header(result, f_out=None):
  from datetime import datetime
  report_time = result.get('date', datetime.utcnow().isoformat())

  print('-- Vigiles CVE Scanner --\n\n'
          '\t%s\n\n' % INFO_PAGE, file=f_out)
  print('-- Date Generated (UTC) --\n', file=f_out)
  print('\t%s' % report_time, file=f_out)


def print_report_overview(result, is_demo=False, f_out=None):
  report_path = result.get('report_path', '')
  product_path = result.get('product_path', '')

  if report_path:
    report_url = '%s%s' % (llapi.LinuxLinkURL, report_path)
    print('\n-- Vigiles CVE Report --', file=f_out)
    print('\n\tView detailed online report at:\n'
            '\t  %s' % report_url, file=f_out)
  elif product_path:
    product_url = '%s%s' % (llapi.LinuxLinkURL, product_path)
    product_name = result.get('product_name', 'Default')
    print('\n-- Vigiles Dashboard --', file=f_out)
    print('\n\tThe manifest has been uploaded to the \'%s\' Product Workspace:\n\n'
            '\t  %s\n' % (product_name, product_url), file=f_out)

  if (is_demo):
    print('\t  NOTE: Running in Demo Mode will cause this URL to expire '
      'after one day.', file=f_out)


def print_summary(result, outfile=None):

    def show_subscribed_summary(f_out=outfile):
      counts = result.get('counts', {})
      unfixed = parse_cve_counts(counts, 'unfixed')
      unapplied = parse_cve_counts(counts, 'unapplied')
      fixed = parse_cve_counts(counts, 'fixed')

      cvss_counts = counts.get('cvss_counts', {})
      cvss_total = parse_cvss_counts(cvss_counts, 'high')
      cvss_kernel = parse_cvss_counts(cvss_counts.get('kernel', {}), 'high')
      cvss_toolchain = parse_cvss_counts(cvss_counts.get('toolchain', {}), 'high')
      cvss_rfs = cvss_total - cvss_kernel - cvss_toolchain

      print('\n\tUnfixed: {} ({} RFS, {} Kernel, {} Toolchain)'.format(
              unfixed['total'], unfixed['rfs'],
              unfixed['kernel'], unfixed['toolchain']),
            file=f_out)
      print('\tUnfixed, Patch Available: '
            '{} ({} RFS, {} Kernel, {} Toolchain)'.format(
              unapplied['total'], unapplied['rfs'],
              unapplied['kernel'], unapplied['toolchain']),
            file=f_out)
      print('\tFixed: {} ({} RFS, {} Kernel, {} Toolchain)'.format(
              fixed['total'], fixed['rfs'], fixed['kernel'], fixed['toolchain']),
            file=f_out)
      print('\tHigh CVSS: {} ({} RFS, {} Kernel, {} Toolchain)'.format(
              cvss_total, cvss_rfs, cvss_kernel, cvss_toolchain),
            file=f_out)

    def show_demo_summary(f_out=outfile):
      cves = result.get('cves', {})
      print('\n-- Vigiles CVE Overview --', file=f_out)
      print('\n\tUnfixed: %d\n'
      '\tUnfixed, Patch Available: %d\n'
      '\tFixed: %d'
      % (cves['unfixed_count'],
         cves['unapplied_count'],
         cves['fixed_count']),
            file=f_out)

    is_demo = result.get('demo', False)

    if 'counts' in result:
      show_subscribed_summary(outfile)
    elif is_demo:
      show_demo_summary(outfile)


def print_foootnotes(f_out=None):
    print('\n-- Vigiles Footnotes --', file=f_out)
    print('\t* "CPU" CVEs are filed against the hardware.\n'
          '\t  They may be fixed or mitigated in other components such as '
                'the kernel or compiler.\n',
          file=f_out)

    print('\t* "Patch Available" CVEs have a fix available in the '
                'meta-timesys-security layer.\n'
          '\t  If the layer is already included, then you may need to '
                'update your copy.\n',
          file=f_out)

    print('\t* "Whitelist" Recipes and CVEs are listed in the '
                '"VIGILES_WHITELIST" variable.\n'
          '\t  They are NOT included in the report.\n',
      file=f_out)


def print_whitelist(wl, outfile=None):
    print('\n-- Vigiles CVE Whitelist --\n', file=outfile)
    if wl:
        for item in sorted(wl):
            print('\t* %s' % item, file=outfile)
    else:
            print('\t(Nothing is Whitelisted)', file=outfile)


def _get_credentials(kf_param, dc_param, sf_param):
    home_dir = os.path.expanduser('~')
    timesys_dir  = os.path.join(home_dir, 'timesys')

    c_env = os.getenv('VIGILES_API_CREDENTIALS', '')

    kf_env = os.getenv('VIGILES_KEY_FILE', '')
    kf_default = os.path.join(timesys_dir, 'linuxlink_key')

    dc_env = os.getenv('VIGILES_DASHBOARD_CONFIG', '')
    dc_default = os.path.join(timesys_dir, 'dashboard_config')

    sf_env = os.getenv('VIGILES_SUBFOLDER_NAME', '')
    sf_default = ''

    if c_env:
        print("Vigiles: Using LinuxLink Credentials in Environment")
    elif kf_env:
        print("Vigiles: Using LinuxLink Key from Environment: %s" % kf_env)
        key_file = kf_env
    elif kf_param:
        print("Vigiles: Using LinuxLink Key from Configuration: %s" % kf_param)
        key_file = kf_param
    else:
        print("Vigiles: Trying LinuxLink Key Default: %s" % kf_default)
        key_file = kf_default

    if dc_env:
        print("Vigiles: Using Dashboard Config from Environment: %s" % dc_env)
        dashboard_config = dc_env
    elif dc_param:
        print("Vigiles: Using Dashboard Config Configuration: %s" % dc_param)
        dashboard_config = dc_param
    else:
        print("Vigiles: Trying Dashboard Config Default: %s" % dc_default)
        dashboard_config = dc_default

    if sf_env:
        print("Vigiles: Using Subfolder Name from Environment: %s" % sf_env)
        subfolder_name = sf_env
    elif sf_param:
        print("Vigiles: Using Subfolder Name from Configuration: %s" % sf_param)
        subfolder_name = sf_param
    else:
        print("Vigiles: Using Subfolder Name Default: %s" % sf_default)
        subfolder_name = sf_default

    try:
        email, key = (None, None)

        # If Vigiles API credentials are specified in the environment, they
        # are used by default instead of the keyfile.
        if c_env:
            creds = json.loads(c_env)
            email, key = llapi.parse_credentials(creds)
        else:
            email, key = llapi.read_keyfile(key_file)

        # It is fine if either of these are none, they will just default
        dashboard_tokens = llapi.read_dashboard_config(dashboard_config)
    except Exception as e:
        print('Error: %s\n' % e)
        print(get_usage())
        sys.exit(1)

    vgls_creds = {
        'email': email,
        'key': key,
        'product': dashboard_tokens.get('product', ''),
        'folder': dashboard_tokens.get('folder', ''),
        'subfolder_name': subfolder_name,
    }
    return vgls_creds

if __name__ == '__main__':
    resource = '/api/v1/vigiles/manifests'
    demo = False
    args = handle_cmdline_args()

    vgls_creds = _get_credentials(args.llkey, args.lldashboard, args.subfolder_name)
    email = vgls_creds['email']
    key = vgls_creds['key']

    # If there was no proper API keyfile, operate in demo mode.
    if not email or not key:
        demo = True
        resource += '/demo'
        print_demo_notice(bad_key=True)

    upload_only = args.upload_only

    if args.outfile:
        outfile = open(args.outfile, 'w')
    else:
        outfile = None

    manifest_data = read_manifest(args.manifest)
    m = json.loads(manifest_data)
    if len(m['packages']) == 0:
        print('No packages found in manifest.\n')
        sys.exit(1)

    manifest = json.loads(manifest_data)

    # If -k is specified, the given config file is submitted along with the
    # manifest to filter out irrelevant kernel CVEs
    if not args.kconfig:
        kernel_config = ''
    else:
        try:
            with open(args.kconfig, 'r') as kconfig:
                kernel_config = kconfig.read().strip()
        except (OSError, IOError, UnicodeDecodeError) as e:
            print('Error: Could not open kernel config: %s' % e)
            sys.exit(1)
        print('Vigiles: Kernel Config based filtering has been applied', file=sys.stderr)

    # U-Boot and SPL filtering works the same way as kernel config filtering
    if not args.uboot_config:
        uboot_config = ''
    else:
        try:
            with open(args.uboot_config, 'r') as uconfig:
                uboot_config = uconfig.read().strip()
        except (OSError, IOError, UnicodeDecodeError) as e:
            print('Error: Could not open U-Boot config: %s' % e)
            sys.exit(1)
        print('Vigiles: U-Boot Config based filtering has been applied', file=sys.stderr)

    request = {
      'manifest': manifest_data,
      'subscribe': args.subscribe,
      'product_token': vgls_creds.get('product', ''),
      'folder_token': vgls_creds.get('folder', ''),
      'subfolder_name': vgls_creds.get('subfolder_name', ''),
      'upload_only': upload_only,
    }

    if kernel_config:
      request['kernel_config'] = kernel_config

    if uboot_config:
      request['uboot_config'] = uboot_config

    _image = manifest.get('image', '')
    _name = manifest.get('manifest_name', _image)
    print('Vigiles: Requesting image analysis from LinuxLink for %s (%s) \n'
          % (_name, _image), file=sys.stderr)

    result = llapi.api_post(email, key, resource, request)

    if not result:
      sys.exit(1)

    # the default list contains a harmless but bogus example CVE ID,
    # don't print it here in case that is confusing.
    whitelist = [ item for item in manifest.get('whitelist', []) 
      if not any(bogon == item for bogon in bogus_whitelist.split()) ]

    # If no LinuxLink subscription or bogus user/key, it will have fallen back
    # to demo mode
    demo_result = result.get('demo', False)
    if not demo and demo_result:
        print_demo_notice()
        demo = demo_result

    # If notification subscription was requested but there was no LinuxLink
    # account / seat:
    sub_result = result.get('subscribed', False)
    if args.subscribe:
        print('\n-- Vigiles CVE Weekly Report --\n', file=outfile)
        if not sub_result:
            print('\tWarning: Could not subscribe to weekly CVE report!\n'
                '\t  Please check that you have an active LinuxLink '
                'subscription.\n', file=outfile)
        else:
            print('\tNotice: You subscribed to weekly email notifications for '
                  'this report.\n'
                  '\tMake sure that you are allowing update emails in your '
                  'LinuxLink preferences.\n', file=outfile)

    print_report_header(result, outfile)
    print_report_overview(result, demo, outfile)

    print_summary(result, outfile=outfile)

    if not demo:
      print_cves(result, outfile=outfile)

    if not upload_only:
      print_whitelist(whitelist, outfile=outfile)
      print_foootnotes(f_out=outfile)

    if outfile is not None:
      print_report_overview(result, demo)
      print_summary(result)
      print('\n\tLocal summary written to:\n\t  %s' %
            os.path.relpath(outfile.name))

#!/usr/bin/env python3
#
# This file is part of the MicroPython project, http://micropython.org/
#
# The MIT License (MIT)
#
# Copyright (c) 2019 Damien P. George
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

from __future__ import print_function
import sys
import os
import subprocess


###########################################################################
# Public functions to be used in the manifest

def include(manifest):
    """Include another manifest.

    The manifest argument can be a string (filename) or an iterable of
    strings.

    Relative paths are resolved with respect to the current manifest file.
    """

    if not isinstance(manifest, str):
        for m in manifest:
            include(m)
    else:
        manifest = convert_path(manifest)
        with open(manifest) as f:
            # Make paths relative to this manifest file while processing it.
            # Applies to includes and input files.
            prev_cwd = os.getcwd()
            os.chdir(os.path.dirname(manifest))
            exec(f.read())
            os.chdir(prev_cwd)

def freeze(path, script=None, opt=0):
    """Freeze the input, automatically determining its type.  A .py script
    will be compiled to a .mpy first then frozen, and a .mpy file will be
    frozen directly.

    `path` must be a directory, which is the base directory to search for
    files from.  When importing the resulting frozen modules, the name of
    the module will start after `path`, ie `path` is excluded from the
    module name.

    If `path` is relative, it is resolved to the current manifest.py.
    Use $(MPY_DIR), $(MPY_LIB_DIR), $(PORT_DIR), $(BOARD_DIR) if you need
    to access specific paths.

    If `script` is None all files in `path` will be frozen.

    If `script` is an iterable then freeze() is called on all items of the
    iterable (with the same `path` and `opt` passed through).

    If `script` is a string then it specifies the filename to freeze, and
    can include extra directories before the file.  The file will be
    searched for in `path`.

    `opt` is the optimisation level to pass to mpy-cross when compiling .py
    to .mpy.
    """

    freeze_internal(KIND_AUTO, path, script, opt)

def freeze_as_str(path):
    """Freeze the given `path` and all .py scripts within it as a string,
    which will be compiled upon import.
    """

    freeze_internal(KIND_AS_STR, path, None, 0)

def freeze_as_mpy(path, script=None, opt=0):
    """Freeze the input (see above) by first compiling the .py scripts to
    .mpy files, then freezing the resulting .mpy files.
    """

    freeze_internal(KIND_AS_MPY, path, script, opt)

def freeze_mpy(path, script=None, opt=0):
    """Freeze the input (see above), which must be .mpy files that are
    frozen directly.
    """

    freeze_internal(KIND_MPY, path, script, opt)


###########################################################################
# Internal implementation

KIND_AUTO = 0
KIND_AS_STR = 1
KIND_AS_MPY = 2
KIND_MPY = 3

VARS = {}

manifest_list = []

class FreezeError(Exception):
    pass

def system(cmd):
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        return 0, output
    except subprocess.CalledProcessError as er:
        return -1, er.output

def convert_path(path):
    # Perform variable substituion.
    for name, value in VARS.items():
        path = path.replace('$({})'.format(name), value)
    # Convert to absolute path (so that future operations don't rely on
    # still being chdir'ed).
    return os.path.abspath(path)

def get_timestamp(path, default=None):
    try:
        stat = os.stat(path)
        return stat.st_mtime
    except OSError:
        if default is None:
            raise FreezeError('cannot stat {}'.format(path))
        return default

def get_timestamp_newest(path):
    ts_newest = 0
    for dirpath, dirnames, filenames in os.walk(path, followlinks=True):
        for f in filenames:
            ts_newest = max(ts_newest, get_timestamp(os.path.join(dirpath, f)))
    return ts_newest

def mkdir(path):
    cur_path = ''
    for p in path.split('/')[:-1]:
        cur_path += p + '/'
        try:
            os.mkdir(cur_path)
        except OSError as er:
            if er.args[0] == 17: # file exists
                pass
            else:
                raise er

def freeze_internal(kind, path, script, opt):
    path = convert_path(path)
    if script is None and kind == KIND_AS_STR:
        if any(f[0] == KIND_AS_STR for f in manifest_list):
            raise FreezeError('can only freeze one str directory')
        manifest_list.append((KIND_AS_STR, path, script, opt))
    elif script is None:
        for dirpath, dirnames, filenames in os.walk(path, followlinks=True):
            for f in filenames:
                freeze_internal(kind, path, (dirpath + '/' + f)[len(path) + 1:], opt)
    elif not isinstance(script, str):
        for s in script:
            freeze_internal(kind, path, s, opt)
    else:
        extension_kind = {KIND_AS_MPY: '.py', KIND_MPY: '.mpy'}
        if kind == KIND_AUTO:
            for k, ext in extension_kind.items():
                if script.endswith(ext):
                    kind = k
                    break
            else:
                print('warn: unsupported file type, skipped freeze: {}'.format(script))
                return
        wanted_extension = extension_kind[kind]
        if not script.endswith(wanted_extension):
            raise FreezeError('expecting a {} file, got {}'.format(wanted_extension, script))
        manifest_list.append((kind, path, script, opt))

def main():
    # Parse arguments
    import argparse
    cmd_parser = argparse.ArgumentParser(description='A tool to generate frozen content in MicroPython firmware images.')
    cmd_parser.add_argument('-o', '--output', help='output path')
    cmd_parser.add_argument('-b', '--build-dir', help='output path')
    cmd_parser.add_argument('-f', '--mpy-cross-flags', default='', help='flags to pass to mpy-cross')
    cmd_parser.add_argument('-v', '--var', action='append', help='variables to substitute')
    cmd_parser.add_argument('files', nargs='+', help='input manifest list')
    args = cmd_parser.parse_args()

    # Extract variables for substitution.
    for var in args.var:
        name, value = var.split('=', 1)
        if os.path.exists(value):
            value = os.path.abspath(value)
        VARS[name] = value

    if 'MPY_DIR' not in VARS or 'PORT_DIR' not in VARS:
        print('MPY_DIR and PORT_DIR variables must be specified')
        sys.exit(1)

    # Get paths to tools
    MAKE_FROZEN = VARS['MPY_DIR'] + '/tools/make-frozen.py'
    MPY_CROSS = VARS['MPY_DIR'] + '/mpy-cross/mpy-cross'
    MPY_TOOL = VARS['MPY_DIR'] + '/tools/mpy-tool.py'

    # Ensure mpy-cross is built
    if not os.path.exists(MPY_CROSS):
        print('mpy-cross not found at {}, please build it first'.format(MPY_CROSS))
        sys.exit(1)

    # Include top-level inputs, to generate the manifest
    for input_manifest in args.files:
        try:
            if input_manifest.endswith('.py'):
                include(input_manifest)
            else:
                exec(input_manifest)
        except FreezeError as er:
            print('freeze error executing "{}": {}'.format(input_manifest, er.args[0]))
            sys.exit(1)

    # Process the manifest
    str_paths = []
    mpy_files = []
    ts_newest = 0
    for kind, path, script, opt in manifest_list:
        if kind == KIND_AS_STR:
            str_paths.append(path)
            ts_outfile = get_timestamp_newest(path)
        elif kind == KIND_AS_MPY:
            infile = '{}/{}'.format(path, script)
            outfile = '{}/frozen_mpy/{}.mpy'.format(args.build_dir, script[:-3])
            ts_infile = get_timestamp(infile)
            ts_outfile = get_timestamp(outfile, 0)
            if ts_infile >= ts_outfile:
                print('MPY', script)
                mkdir(outfile)
                res, out = system([MPY_CROSS] + args.mpy_cross_flags.split() + ['-o', outfile, '-s', script, '-O{}'.format(opt), infile])
                if res != 0:
                    print('error compiling {}: {}'.format(infile, out))
                    raise SystemExit(1)
                ts_outfile = get_timestamp(outfile)
            mpy_files.append(outfile)
        else:
            assert kind == KIND_MPY
            infile = '{}/{}'.format(path, script)
            mpy_files.append(infile)
            ts_outfile = get_timestamp(infile)
        ts_newest = max(ts_newest, ts_outfile)

    # Check if output file needs generating
    if ts_newest < get_timestamp(args.output, 0):
        # No files are newer than output file so it does not need updating
        return

    # Freeze paths as strings
    res, output_str = system([sys.executable, MAKE_FROZEN] + str_paths)
    if res != 0:
        print('error freezing strings {}: {}'.format(str_paths, output_str))
        sys.exit(1)

    # Freeze .mpy files
    res, output_mpy = system([sys.executable, MPY_TOOL, '-f', '-q', args.build_dir + '/genhdr/qstrdefs.preprocessed.h'] + mpy_files)
    if res != 0:
        print('error freezing mpy {}: {}'.format(mpy_files, output_mpy))
        sys.exit(1)

    # Generate output
    print('GEN', args.output)
    mkdir(args.output)
    with open(args.output, 'wb') as f:
        f.write(b'//\n// Content for MICROPY_MODULE_FROZEN_STR\n//\n')
        f.write(output_str)
        f.write(b'//\n// Content for MICROPY_MODULE_FROZEN_MPY\n//\n')
        f.write(output_mpy)

if __name__ == '__main__':
    main()

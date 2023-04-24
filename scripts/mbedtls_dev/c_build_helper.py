"""Generate and run C code.
"""

# Copyright The Mbed TLS Contributors
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import platform
import subprocess
import sys
import tempfile

def remove_file_if_exists(filename):
    """Remove the specified file, ignoring errors."""
    if not filename:
        return
    try:
        os.remove(filename)
    except OSError:
        pass

def create_c_file(file_label):
    """Create a temporary C file.

    * ``file_label``: a string that will be included in the file name.

    Return ```(c_file, c_name, exe_name)``` where ``c_file`` is a Python
    stream open for writing to the file, ``c_name`` is the name of the file
    and ``exe_name`` is the name of the executable that will be produced
    by compiling the file.
    """
    c_fd, c_name = tempfile.mkstemp(prefix='tmp-{}-'.format(file_label),
                                    suffix='.c')
    exe_suffix = '.exe' if platform.system() == 'Windows' else ''
    exe_name = c_name[:-2] + exe_suffix
    remove_file_if_exists(exe_name)
    c_file = os.fdopen(c_fd, 'w', encoding='ascii')
    return c_file, c_name, exe_name

def generate_c_printf_expressions(c_file, cast_to, printf_format, expressions):
    """Generate C instructions to print the value of ``expressions``.

    Write the code with ``c_file``'s ``write`` method.

    Each expression is cast to the type ``cast_to`` and printed with the
    printf format ``printf_format``.
    """
    for expr in expressions:
        c_file.write('    printf("{}\\n", ({}) {});\n'
                     .format(printf_format, cast_to, expr))

def generate_c_file(c_file,
                    caller, header,
                    main_generator):
    """Generate a temporary C source file.

    * ``c_file`` is an open stream on the C source file.
    * ``caller``: an informational string written in a comment at the top
      of the file.
    * ``header``: extra code to insert before any function in the generated
      C file.
    * ``main_generator``: a function called with ``c_file`` as its sole argument
      to generate the body of the ``main()`` function.
    """
    c_file.write('/* Generated by {} */'
                 .format(caller))
    c_file.write('''
#include <stdio.h>
''')
    c_file.write(header)
    c_file.write('''
int main(void)
{
''')
    main_generator(c_file)
    c_file.write('''    return 0;
}
''')

def compile_c_file(c_filename, exe_filename, include_dirs):
    """Compile a C source file with the host compiler.

    * ``c_filename``: the name of the source file to compile.
    * ``exe_filename``: the name for the executable to be created.
    * ``include_dirs``: a list of paths to include directories to be passed
      with the -I switch.
    """
    # Respect $HOSTCC if it is set
    cc = os.getenv('HOSTCC', None)
    if cc is None:
        cc = os.getenv('CC', 'cc')
    cmd = [cc]

    proc = subprocess.Popen(cmd,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE,
                            universal_newlines=True)
    cc_is_msvc = 'Microsoft (R) C/C++' in proc.communicate()[1]

    cmd += ['-I' + dir for dir in include_dirs]
    if cc_is_msvc:
        # MSVC has deprecated using -o to specify the output file,
        # and produces an object file in the working directory by default.
        obj_filename = exe_filename[:-4] + '.obj'
        cmd += ['-Fe' + exe_filename, '-Fo' + obj_filename]
    else:
        cmd += ['-o' + exe_filename]

    subprocess.check_call(cmd + [c_filename])

def get_c_expression_values(
        cast_to, printf_format,
        expressions,
        caller=__name__, file_label='',
        header='', include_path=None,
        keep_c=False,
): # pylint: disable=too-many-arguments, too-many-locals
    """Generate and run a program to print out numerical values for expressions.

    * ``cast_to``: a C type.
    * ``printf_format``: a printf format suitable for the type ``cast_to``.
    * ``header``: extra code to insert before any function in the generated
      C file.
    * ``expressions``: a list of C language expressions that have the type
      ``cast_to``.
    * ``include_path``: a list of directories containing header files.
    * ``keep_c``: if true, keep the temporary C file (presumably for debugging
      purposes).

    Use the C compiler specified by the ``CC`` environment variable, defaulting
    to ``cc``. If ``CC`` looks like MSVC, use its command line syntax,
    otherwise assume the compiler supports Unix traditional ``-I`` and ``-o``.

    Return the list of values of the ``expressions``.
    """
    if include_path is None:
        include_path = []
    c_name = None
    exe_name = None
    obj_name = None
    try:
        c_file, c_name, exe_name = create_c_file(file_label)
        generate_c_file(
            c_file, caller, header,
            lambda c_file: generate_c_printf_expressions(c_file,
                                                         cast_to, printf_format,
                                                         expressions)
        )
        c_file.close()

        compile_c_file(c_name, exe_name, include_path)
        if keep_c:
            sys.stderr.write('List of {} tests kept at {}\n'
                             .format(caller, c_name))
        else:
            os.remove(c_name)
        output = subprocess.check_output([exe_name])
        return output.decode('ascii').strip().split('\n')
    finally:
        remove_file_if_exists(exe_name)
        remove_file_if_exists(obj_name)

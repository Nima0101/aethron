# SPDX-License-Identifier: GPL-3.0-only
import cython

@cython.locals(payload=bytes, char=cython.uchar, depth=cython.int,
               quoted=cython.bint, escaped=cython.bint)
cpdef bint check(object data)

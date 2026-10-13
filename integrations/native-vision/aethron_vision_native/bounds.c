#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <float.h>
#include <stdint.h>
#include <string.h>

#if FLT_RADIX != 2 || FLT_MANT_DIG != 24 || FLT_MAX_EXP != 128
#error "IEEE binary32 float is required"
#endif

static PyObject *invalid_input(void) {
    PyErr_SetString(PyExc_ValueError, "invalid_input");
    return NULL;
}

static PyObject *validate_output(PyObject *self, PyObject *arg) {
    (void)self;
    Py_buffer view;
    if (PyObject_GetBuffer(arg, &view, PyBUF_C_CONTIGUOUS | PyBUF_FORMAT) < 0) {
        PyErr_Clear();
        return invalid_input();
    }
    int format_ok = view.format &&
        (strcmp(view.format, "f") == 0 || strcmp(view.format, "=f") == 0 ||
         strcmp(view.format, "@f") == 0);
    int shape_ok = view.ndim == 3 && view.shape && view.shape[0] == 1 &&
        view.shape[1] == 8400 && view.shape[2] == 85;
    if (sizeof(float) != 4 || view.itemsize != 4 || view.len != 2856000 ||
        !view.buf || !format_ok || !shape_ok || view.suboffsets ||
        !PyBuffer_IsContiguous(&view, 'C')) {
        PyBuffer_Release(&view);
        return invalid_input();
    }
    const char *base = (const char *)view.buf;
    unsigned valid = 1;
    /* Keep the GIL and buffer export. No allocation, retained pointer or writes.
       memcpy handles even an unaligned native-endian binary32 buffer safely. */
    for (Py_ssize_t row = 0; row < 8400; ++row) {
        for (Py_ssize_t col = 0; col < 4; ++col) {
            float value;
            memcpy(&value, base + (row * 85 + col) * 4, 4);
            valid &= (value >= -FLT_MAX) & (value <= FLT_MAX);
        }
        for (Py_ssize_t col = 4; col < 85; ++col) {
            float value;
            memcpy(&value, base + (row * 85 + col) * 4, 4);
            valid &= (value >= 0) & (value <= 1);
        }
    }
    PyBuffer_Release(&view);
    return PyBool_FromLong(valid);
}

static void pack_channels(const unsigned char *restrict source,
                          unsigned char *restrict output) {
    for (size_t channel = 0; channel < 3; ++channel) {
        for (size_t pixel = 0; pixel < 640 * 640; ++pixel) {
            float value = source[pixel * 3 + channel];
            memcpy(output + (channel * 640 * 640 + pixel) * 4, &value, 4);
        }
    }
}

static PyObject *pack_rgb(PyObject *self, PyObject *args) {
    (void)self;
    PyObject *source, *output;
    Py_buffer src, dst;
    if (!PyArg_ParseTuple(args, "OO", &source, &output)) {
        PyErr_Clear();
        return invalid_input();
    }
    if (PyObject_GetBuffer(source, &src, PyBUF_C_CONTIGUOUS | PyBUF_FORMAT) < 0) {
        PyErr_Clear();
        return invalid_input();
    }
    if (PyObject_GetBuffer(output, &dst, PyBUF_C_CONTIGUOUS | PyBUF_FORMAT | PyBUF_WRITABLE) < 0) {
        PyBuffer_Release(&src);
        PyErr_Clear();
        return invalid_input();
    }
    int valid = sizeof(float) == 4 && src.buf && dst.buf &&
        src.itemsize == 1 && src.len == 1228800 && src.ndim == 3 &&
        src.shape && src.shape[0] == 640 && src.shape[1] == 640 && src.shape[2] == 3 &&
        src.format && strcmp(src.format, "B") == 0 && !src.suboffsets &&
        dst.itemsize == 4 && dst.len == 4915200 && dst.ndim == 4 &&
        dst.shape && dst.shape[0] == 1 && dst.shape[1] == 3 &&
        dst.shape[2] == 640 && dst.shape[3] == 640 && !dst.suboffsets &&
        dst.format && (strcmp(dst.format, "f") == 0 || strcmp(dst.format, "=f") == 0 ||
                       strcmp(dst.format, "@f") == 0) &&
        PyBuffer_IsContiguous(&src, 'C') && PyBuffer_IsContiguous(&dst, 'C');
    if (valid) {
        uintptr_t a = (uintptr_t)src.buf, b = (uintptr_t)dst.buf;
        valid = a <= UINTPTR_MAX - 1228800 && b <= UINTPTR_MAX - 4915200 &&
            (a + 1228800 <= b || b + 4915200 <= a);
    }
    if (valid) {
        pack_channels((const unsigned char *)src.buf, (unsigned char *)dst.buf);
    }
    PyBuffer_Release(&dst);
    PyBuffer_Release(&src);
    if (!valid) return invalid_input();
    return PyBool_FromLong(1);
}

static PyMethodDef methods[] = {
    {"validate_output", validate_output, METH_O, "Check a bounded contiguous float32 output."},
    {"pack_rgb", pack_rgb, METH_VARARGS, "Pack a fixed RGB canvas into caller-owned float32 NCHW."},
    {NULL, NULL, 0, NULL}
};
static struct PyModuleDef module = {
    PyModuleDef_HEAD_INIT, "_bounds", NULL, -1, methods, NULL, NULL, NULL, NULL
};
PyMODINIT_FUNC PyInit__bounds(void) {
    return PyModule_Create(&module);
}

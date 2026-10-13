#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <float.h>
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

static PyMethodDef methods[] = {
    {"validate_output", validate_output, METH_O, "Check a bounded contiguous float32 output."},
    {NULL, NULL, 0, NULL}
};
static struct PyModuleDef module = {
    PyModuleDef_HEAD_INIT, "_bounds", NULL, -1, methods, NULL, NULL, NULL, NULL
};
PyMODINIT_FUNC PyInit__bounds(void) {
    return PyModule_Create(&module);
}

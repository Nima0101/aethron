// SPDX-License-Identifier: GPL-3.0-only
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include "kernel.hpp"

static PyObject* remap(PyObject*, PyObject* args) {
    const char* source=nullptr;
    Py_ssize_t size=0;
    aethron::Brown c{};
    if (!PyArg_ParseTuple(args,"y#(iiiiiii)(dddddddddddddd)",&source,&size,
        &c.width,&c.height,&c.step,&c.bytes,&c.big,&c.out_width,&c.out_height,
        &c.p[0],&c.p[1],&c.p[2],&c.p[3],&c.p[4],&c.p[5],&c.p[6],&c.p[7],
        &c.p[8],&c.p[9],&c.p[10],&c.p[11],&c.p[12],&c.p[13])) return nullptr;
    if (!PyBytes_CheckExact(PyTuple_GetItem(args,0)) || c.out_width<1 || c.out_width>1920 ||
        c.out_height<1 || c.out_height>1080 || (c.bytes!=1 && c.bytes!=2)) {
        PyErr_SetString(PyExc_ValueError,"invalid_native_raster"); return nullptr;
    }
    const auto pixels=static_cast<Py_ssize_t>(c.out_width)*c.out_height;
    if (pixels>640*512) { PyErr_SetString(PyExc_ValueError,"invalid_native_raster"); return nullptr; }
    PyObject* data=PyBytes_FromStringAndSize(nullptr,pixels*c.bytes);
    if (!data) return nullptr;
    PyObject* mask=PyBytes_FromStringAndSize(nullptr,pixels);
    if (!mask) { Py_DECREF(data); return nullptr; }
    auto* d=reinterpret_cast<std::uint8_t*>(PyBytes_AS_STRING(data));
    auto* m=reinterpret_cast<std::uint8_t*>(PyBytes_AS_STRING(mask));
    bool ok;
    Py_BEGIN_ALLOW_THREADS
    ok=aethron::remap(c,{reinterpret_cast<const std::uint8_t*>(source),static_cast<std::size_t>(size)},
        {d,static_cast<std::size_t>(pixels*c.bytes)},{m,static_cast<std::size_t>(pixels)});
    Py_END_ALLOW_THREADS
    if (!ok) { Py_DECREF(data); Py_DECREF(mask); PyErr_SetString(PyExc_ValueError,"invalid_native_raster"); return nullptr; }
    return Py_BuildValue("NN",data,mask);
}
static PyMethodDef methods[]={{"remap",remap,METH_VARARGS,"Internal bounded Brown count kernel."},{nullptr,nullptr,0,nullptr}};
static PyModuleDef module={PyModuleDef_HEAD_INIT,"_kernel",nullptr,-1,methods,nullptr,nullptr,nullptr,nullptr};
PyMODINIT_FUNC PyInit__kernel() { return PyModule_Create(&module); }

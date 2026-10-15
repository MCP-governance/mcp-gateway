/*
 * mcpgw_textscan: the Gateway's tool-text rules on PCRE2 (JIT), outside the GIL.
 *
 * Python's re keeps the GIL for the whole match, so a 200 KB tool result held the
 * event loop for ~70 ms. Matching here runs on compiled machine code with the GIL
 * released.
 *
 * The rules must decide exactly as Python's re does. Instead of hoping PCRE2's own
 * Unicode tables and case folding agree with CPython's, every character of the
 * subject is first mapped to a small canonical alphabet using CPython's own
 * functions - the ones _sre uses (Py_UNICODE_TOLOWER, ISALNUM, ISSPACE, ISDECIMAL):
 *
 *   ignore-case view  x -> group(tolower(x)) if that is in the alphabet, else a
 *                     category representative (word+decimal, word, space, other)
 *   exact view        x -> x if in the alphabet, else a category representative
 *
 * group() folds the extra equivalences _sre applies under IGNORECASE (i/ı, s/ſ ...),
 * passed in from re._compiler. The alphabet holds every character the rules name
 * plus ASCII. app/textscan.py translates each rule into PCRE2 syntax over that
 * alphabet with explicit classes only, so no PCRE2 Unicode or caseless semantics are
 * involved. tests/textscan_parity_check.py checks every atom of every rule against
 * re over all code points and differential-fuzzes whole rules.
 */
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#define PCRE2_CODE_UNIT_WIDTH 32
#include <pcre2.h>
#include <stdint.h>
#include <string.h>

#define CODEPOINTS 0x110000u

typedef struct {
    PyObject_HEAD
    uint32_t *exact;      /* CODEPOINTS entries */
    uint32_t *folded;     /* CODEPOINTS entries */
    pcre2_code **codes;
    int *ignorecase;
    Py_ssize_t count;
    Py_ssize_t capacity;
} Engine;

static void engine_dealloc(Engine *self) {
    for (Py_ssize_t i = 0; i < self->count; i++) pcre2_code_free(self->codes[i]);
    PyMem_Free(self->codes);
    PyMem_Free(self->ignorecase);
    PyMem_Free(self->exact);
    PyMem_Free(self->folded);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static uint32_t category(Py_UCS4 c, const uint32_t reps[4]) {
    /* reps: word+decimal, word, space, other */
    if (Py_UNICODE_ISALNUM(c) || c == '_') return Py_UNICODE_ISDECIMAL(c) ? reps[0] : reps[1];
    if (Py_UNICODE_ISSPACE(c)) return reps[2];
    return reps[3];
}

/* Engine(alphabet: str, representatives: str of 4, groups: dict[int, int]) */
static int engine_init(Engine *self, PyObject *args, PyObject *kwds) {
    PyObject *alphabet, *reps_obj, *groups;
    if (!PyArg_ParseTuple(args, "UUO!", &alphabet, &reps_obj, &PyDict_Type, &groups)) return -1;
    if (PyUnicode_GET_LENGTH(reps_obj) != 4) {
        PyErr_SetString(PyExc_ValueError, "four representatives required");
        return -1;
    }
    uint32_t reps[4];
    for (int i = 0; i < 4; i++) reps[i] = PyUnicode_READ_CHAR(reps_obj, i);
    uint8_t *member = PyMem_Calloc(CODEPOINTS, 1);
    uint32_t *group = PyMem_Malloc(sizeof(uint32_t) * CODEPOINTS);
    self->exact = PyMem_Malloc(sizeof(uint32_t) * CODEPOINTS);
    self->folded = PyMem_Malloc(sizeof(uint32_t) * CODEPOINTS);
    if (!member || !group || !self->exact || !self->folded) {
        PyMem_Free(member);
        PyMem_Free(group);
        PyErr_NoMemory();
        return -1;
    }
    Py_ssize_t n = PyUnicode_GET_LENGTH(alphabet);
    for (Py_ssize_t i = 0; i < n; i++) member[PyUnicode_READ_CHAR(alphabet, i)] = 1;
    for (uint32_t c = 0; c < CODEPOINTS; c++) group[c] = c;
    PyObject *key, *value;
    Py_ssize_t pos = 0;
    while (PyDict_Next(groups, &pos, &key, &value)) {
        unsigned long k = PyLong_AsUnsignedLong(key), v = PyLong_AsUnsignedLong(value);
        if (PyErr_Occurred() || k >= CODEPOINTS || v >= CODEPOINTS) {
            PyMem_Free(member);
            PyMem_Free(group);
            if (!PyErr_Occurred()) PyErr_SetString(PyExc_ValueError, "group outside Unicode");
            return -1;
        }
        group[k] = (uint32_t)v;
    }
    for (uint32_t c = 0; c < CODEPOINTS; c++) {
        self->exact[c] = member[c] ? c : category(c, reps);
        uint32_t low = group[(uint32_t)Py_UNICODE_TOLOWER(c)];
        self->folded[c] = member[low] ? low : category(c, reps);
    }
    PyMem_Free(member);
    PyMem_Free(group);
    return 0;
}

/* add(pattern: str, ignorecase: bool) -> index */
static PyObject *engine_add(Engine *self, PyObject *args) {
    PyObject *pattern;
    int ignorecase;
    if (!PyArg_ParseTuple(args, "Up", &pattern, &ignorecase)) return NULL;
    Py_UCS4 *units = PyUnicode_AsUCS4Copy(pattern);
    if (!units) return NULL;
    int error;
    PCRE2_SIZE offset;
    pcre2_code *code = pcre2_compile((PCRE2_SPTR)units, (PCRE2_SIZE)PyUnicode_GET_LENGTH(pattern),
                                     PCRE2_NEVER_UTF | PCRE2_NEVER_UCP | PCRE2_NO_AUTO_CAPTURE, &error, &offset, NULL);
    PyMem_Free(units);
    if (!code) {
        PCRE2_UCHAR message[256];
        pcre2_get_error_message(error, message, 256);
        char ascii[256];
        int i = 0;
        for (; i < 255 && message[i]; i++) ascii[i] = message[i] < 128 ? (char)message[i] : '?';
        ascii[i] = 0;
        return PyErr_Format(PyExc_ValueError, "pcre2 compile at %zu: %s", (size_t)offset, ascii);
    }
    if (pcre2_jit_compile(code, PCRE2_JIT_COMPLETE) != 0) {
        /* The interpreter decides the same; only slower. */
    }
    if (self->count == self->capacity) {
        Py_ssize_t capacity = self->capacity ? self->capacity * 2 : 16;
        pcre2_code **codes = PyMem_Realloc(self->codes, sizeof(pcre2_code *) * capacity);
        if (!codes) { pcre2_code_free(code); return PyErr_NoMemory(); }
        self->codes = codes;
        int *flags = PyMem_Realloc(self->ignorecase, sizeof(int) * capacity);
        if (!flags) { pcre2_code_free(code); return PyErr_NoMemory(); }
        self->ignorecase = flags;
        self->capacity = capacity;
    }
    self->codes[self->count] = code;
    self->ignorecase[self->count] = ignorecase;
    return PyLong_FromSsize_t(self->count++);
}

/* search(text: str, indexes: sequence[int]) -> tuple[bool, ...]; ValueError if PCRE2 fails. */
static PyObject *engine_search(Engine *self, PyObject *args) {
    PyObject *text, *indexes;
    if (!PyArg_ParseTuple(args, "UO", &text, &indexes)) return NULL;
    PyObject *seq = PySequence_Fast(indexes, "indexes must be a sequence");
    if (!seq) return NULL;
    Py_ssize_t wanted = PySequence_Fast_GET_SIZE(seq);
    Py_ssize_t *which = PyMem_Malloc(sizeof(Py_ssize_t) * (wanted ? wanted : 1));
    if (!which) { Py_DECREF(seq); return PyErr_NoMemory(); }
    int need_exact = 0, need_folded = 0;
    for (Py_ssize_t i = 0; i < wanted; i++) {
        Py_ssize_t index = PyLong_AsSsize_t(PySequence_Fast_GET_ITEM(seq, i));
        if (index < 0 || index >= self->count) {
            PyMem_Free(which);
            Py_DECREF(seq);
            if (!PyErr_Occurred()) PyErr_SetString(PyExc_IndexError, "unknown rule");
            return NULL;
        }
        which[i] = index;
        if (self->ignorecase[index]) need_folded = 1; else need_exact = 1;
    }
    Py_DECREF(seq);
    Py_ssize_t length = PyUnicode_GET_LENGTH(text);
    int kind = PyUnicode_KIND(text);
    const void *data = PyUnicode_DATA(text);
    uint32_t *exact = need_exact ? PyMem_RawMalloc(sizeof(uint32_t) * (length ? length : 1)) : NULL;
    uint32_t *folded = need_folded ? PyMem_RawMalloc(sizeof(uint32_t) * (length ? length : 1)) : NULL;
    int *hits = PyMem_Malloc(sizeof(int) * (wanted ? wanted : 1));
    if ((need_exact && !exact) || (need_folded && !folded) || !hits) {
        PyMem_RawFree(exact);
        PyMem_RawFree(folded);
        PyMem_Free(which);
        PyMem_Free(hits);
        return PyErr_NoMemory();
    }
    int failure = 0;
    Py_BEGIN_ALLOW_THREADS
    for (Py_ssize_t i = 0; i < length; i++) {
        Py_UCS4 c = PyUnicode_READ(kind, data, i);
        if (exact) exact[i] = self->exact[c];
        if (folded) folded[i] = self->folded[c];
    }
    pcre2_match_context *context = pcre2_match_context_create(NULL);
    pcre2_jit_stack *stack = pcre2_jit_stack_create(32 * 1024, 8 * 1024 * 1024, NULL);
    if (!context || !stack) failure = PCRE2_ERROR_NOMEMORY;
    else pcre2_jit_stack_assign(context, NULL, stack);
    for (Py_ssize_t i = 0; i < wanted && !failure; i++) {
        pcre2_code *code = self->codes[which[i]];
        pcre2_match_data *match = pcre2_match_data_create_from_pattern(code, NULL);
        if (!match) { failure = PCRE2_ERROR_NOMEMORY; break; }
        const uint32_t *subject = self->ignorecase[which[i]] ? folded : exact;
        int rc = pcre2_match(code, (PCRE2_SPTR)subject, (PCRE2_SIZE)length, 0, 0, match, context);
        pcre2_match_data_free(match);
        if (rc >= 0) hits[i] = 1;
        else if (rc == PCRE2_ERROR_NOMATCH) hits[i] = 0;
        else failure = rc;
    }
    if (stack) pcre2_jit_stack_free(stack);
    if (context) pcre2_match_context_free(context);
    Py_END_ALLOW_THREADS
    PyMem_RawFree(exact);
    PyMem_RawFree(folded);
    PyMem_Free(which);
    if (failure) {
        PyMem_Free(hits);
        return PyErr_Format(PyExc_ValueError, "pcre2 match failed: %d", failure);
    }
    PyObject *result = PyTuple_New(wanted);
    if (result) {
        for (Py_ssize_t i = 0; i < wanted; i++) {
            PyObject *flag = hits[i] ? Py_True : Py_False;
            Py_INCREF(flag);
            PyTuple_SET_ITEM(result, i, flag);
        }
    }
    PyMem_Free(hits);
    return result;
}

/* canonical(text: str, ignorecase: bool) -> str: the view the rules read, for tests. */
static PyObject *engine_canonical(Engine *self, PyObject *args) {
    PyObject *text;
    int ignorecase;
    if (!PyArg_ParseTuple(args, "Up", &text, &ignorecase)) return NULL;
    Py_ssize_t length = PyUnicode_GET_LENGTH(text);
    Py_UCS4 *out = PyMem_Malloc(sizeof(Py_UCS4) * (length ? length : 1));
    if (!out) return PyErr_NoMemory();
    for (Py_ssize_t i = 0; i < length; i++) {
        Py_UCS4 c = PyUnicode_READ_CHAR(text, i);
        out[i] = ignorecase ? self->folded[c] : self->exact[c];
    }
    PyObject *result = PyUnicode_FromKindAndData(PyUnicode_4BYTE_KIND, out, length);
    PyMem_Free(out);
    return result;
}

static PyMethodDef engine_methods[] = {
    {"add", (PyCFunction)engine_add, METH_VARARGS, NULL},
    {"search", (PyCFunction)engine_search, METH_VARARGS, NULL},
    {"canonical", (PyCFunction)engine_canonical, METH_VARARGS, NULL},
    {NULL, NULL, 0, NULL},
};

static PyTypeObject EngineType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "mcpgw_textscan.Engine",
    .tp_basicsize = sizeof(Engine),
    .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_new = PyType_GenericNew,
    .tp_init = (initproc)engine_init,
    .tp_dealloc = (destructor)engine_dealloc,
    .tp_methods = engine_methods,
};

static struct PyModuleDef module = {PyModuleDef_HEAD_INIT, "mcpgw_textscan", NULL, -1, NULL};

PyMODINIT_FUNC PyInit_mcpgw_textscan(void) {
    if (PyType_Ready(&EngineType) < 0) return NULL;
    PyObject *m = PyModule_Create(&module);
    if (!m) return NULL;
    Py_INCREF(&EngineType);
    if (PyModule_AddObject(m, "Engine", (PyObject *)&EngineType) < 0) {
        Py_DECREF(&EngineType);
        Py_DECREF(m);
        return NULL;
    }
    return m;
}

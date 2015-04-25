import sys, re, os.path
import logging
from pprint import pformat
from string import Template

if sys.version_info[0] >= 3:
    from io import StringIO
else:
    from cStringIO import StringIO

#
#       EXCEPTIONS TO AUTO GENERATION
#

ManualFuncs = {
    "core" : [
         [ "class cv.Mat" , "", [], [] ],
         [ "cv.Mat.Mat", "Mat", [], [] ],
         [ "cv.Mat.Mat", "Mat", [],
            [ [ "int", "rows" ], [ "int", "cols" ], [ "int" , "type" ] ] ],
         [ "cv.Mat.depth", "int", ["/C"], [] ],
         [ "cv.Mat.channels", "int", ["/C"], [] ],
         [ "cv.Mat.size", "Size", ["/C"], [] ],
    ]
}

renamed_funcs = {
    "cv_core_divide_MMMDI": "divide_mat",
    "cv_core_norm_MMIM":"norm_dist",
    "cv_core_ellipse_MPSDDDSIII": "ellipse_tilted",
    "cv_core_Mat_Mat_III": "for_rows_and_cols",
    "cv_calib3d_StereoSGBM_StereoSGBM_IIIIIIIIIIB": "for_params",
    "cv_calib3d_StereoBM_StereoBM_III": "for_params",
    "cv_features2d_BOWKMeansTrainer_cluster_M": "cluster_with_desc",
    "cv_features2d_BOWTrainer_cluster_M": "cluster_with_desc",
    "cv_features2d_DescriptorMatcher_match_MMVM" : "matches",
    "cv_features2d_DescriptorMatcher_match_MVV" : "matches",
    "cv_features2d_KeyPoint_KeyPoint_FFFFFII" : "for_params",
    "cv_features2d_DMatch_DMatch_IIF" : "for_params",
    "cv_features2d_DMatch_DMatch_IIIF" : "for_image",
    "cv_features2d_DescriptorMatcher_knnMatch_MMVIMB" : "knnTrainMatch",
    "cv_features2d_DescriptorMatcher_match_MMVM": "trainAndMatch",
    "cv_features2d_BRISK_BRISK_VVFFV" : "for_pattern",
    "cv_highgui_VideoWriter_VideoWriter_SIDSB" : "for_params",
    "cv_highgui_VideoCapture_VideoCapture_S" : "for_file",
    "cv_highgui_VideoCapture_VideoCapture_I" : "for_device",
    "cv_highgui_VideoCapture_open_S" : "open_file",
    "cv_highgui_VideoCapture_open_I" : "open_fd",
    "cv_imgproc_integral_MMMI" : "integral_squares",
    "cv_imgproc_integral_MMMMI" : "integral_squares_tilted",
    "cv_imgproc_distanceTransform_MMMIII" : "distance_tranform_labels",
    "cv_imgproc_Subdiv2D_Subdiv2D_R" : "for_rect",
    "cv_imgproc_Subdiv2D_insert_V" : "insert_multi",
    "cv_objdetect_HOGDescriptor_HOGDescriptor_S": "for_file",
    "cv_objdetect_HOGDescriptor_HOGDescriptor_SSSSIIDIDBI": "for_params",
    "cv_objdetect_CascadeClassifier_detectMultiScale_MVVVDIISSB" : "detectMultiScaleFull",
    "cv_objdetect_CascadeClassifier_CascadeClassifier_S": "for_file",
    "cv_video_calcOpticalFlowSF_MMMIIIDDIDDDIDDD" : "calc_optical_flow_full",
    "cv_video_KalmanFilter_KalmanFilter_IIII" : "for_params",
    "cv_video_BackgroundSubtractorMOG_BackgroundSubtractorMOG_IIDD" : "for_params", 
    "cv_video_BackgroundSubtractorMOG2_BackgroundSubtractorMOG2_IFB" : "for_params", 
}

class_ignore_list = (
    #core
    "FileNode", "FileStorage", "KDTree", "IndexParams", "Params"
    #videoio
#    "VideoWriter",
)

const_ignore_list = (
    "CV_EXPORTS_W", "CV_EXPORTS_W_SIMPLE", "CV_EXPORTS_W_MAP", "CV_MAKE_TYPE",
    "CV_IS_CONT_MAT", "CV_RNG_COEFF", "IPL_IMAGE_MAGIC_VAL",
    "CV_SET_ELEM_FREE_FLAG", "CV_FOURCC_DEFAULT",
    "CV_WHOLE_ARR", "CV_WHOLE_SEQ", "CV_PI", "CV_LOG2",
    "CV_TYPE_NAME_IMAGE", 

)

func_arg_fix = {
}

#
#       TYPES MAPPING
#

primitives = {
    u"void"  : { u"ctype": "void", "rtype": "()" },
    u"bool"  : { u"ctype": "int", u"rtype": "bool" },
    u"uchar" : { u"ctype": "unsigned char", u"rtype": "u8" },
    u"short" : { u"ctype": "short", u"rtype": "u16" },
    u"int"   : { u"ctype": "int", u"rtype": "i32" },
    u"size_t": { u"ctype": "std::size_t", u"rtype": "::libc::types::os::arch::c95::size_t" },
    u"int64" : { u"ctype": "int64", u"rtype": "i64" },
    u"float" : { u"ctype": "float", u"rtype": "f32" },
    u"double": { u"ctype": "double", u"rtype": "f64" }
}

# trait_classes = [ "Algorithm" ]

forced_boxed_classes = { }

value_struct_types = {
    ("core", "Point") : (("x", "int"), ("y", "int")),
    ("core", "Point2d") : (("x", "double"), ("y", "double")),
    ("core", "Point2f") : (("x", "float"), ("y", "float")),
    ("core", "Size") : (("width", "int"), ("height", "int")),
    ("core", "Size2f") : (("width", "float"), ("height", "float")),
    ("core", "Rect") : (("x", "int"), ("y", "int"), ("width", "int"), ("height", "int")),
    ("core", "RotatedRect") : (("x", "float"), ("y", "float"), ("width", "float"),("height", "float"), ("angle", "float")),
    ("core", "TermCriteria") : (("type", "int"), ("maxCount", "int"), ("epsilon", "double")),
    ("core", "Scalar") : (("data", "double[4]"),)
}

for s in [2,3,4,6]:
    for t in [("uchar","b"),("short","s"),("int","i"),("double","d"),("float","f")]:
        value_struct_types[("core","Vec%d%s"%(s,t[1]))] = ("data", "%s[%d]"%(t[0],s)),

#
#       TEMPLATES
#

T_CPP_MODULE = """
//
// This file is auto-generated, please don't edit!
//

#define LOG_TAG "org.opencv.$m"

#include "stdint.h"
#include "common.h"

typedef int64_t int64;

#include "types.h"
#include <iostream>

#include "return_types.h"

#include "opencv2/opencv_modules.hpp"
#ifdef HAVE_OPENCV_$M

#include <string>

#include "opencv2/$m/$m.hpp"
using namespace cv;

$includes

extern "C" {

$code

} // extern "C"

#endif // HAVE_OPENCV_$M
"""

T_RUST_MODULE = """
//
// This file is auto-generated, please don't edit!
//


use ::sys::$m::*;

pub mod $m {
    use sys::types::*;
    use std::ffi::{ CStr, CString };
    use std::mem::transmute;
    use libc::types::common::c95::c_void;
    
    $module_import
    $code
}

"""

const_private_list = (
    "CV_MOP_.+",
    "CV_INTER_.+",
    "CV_THRESH_.+",
    "CV_INPAINT_.+",
    "CV_RETR_.+",
    "CV_CHAIN_APPROX_.+",
    "OPPONENTEXTRACTOR",
    "GRIDDETECTOR",
    "PYRAMIDDETECTOR",
    "DYNAMICDETECTOR",
)

#
#       AST-LIKE
#

class GeneralInfo():
    def __init__(self, gen, name, namespaces):
        self.gen = gen
        self.namespace, self.classpath, self.classname, self.name = self.parseName(name, namespaces)

    def parseName(self, name, namespaces):
        '''
        input: full name and available namespaces
        returns: (namespace, classpath, classname, name)
        '''
        name = name[name.find(" ")+1:].strip() # remove struct/class/const prefix
        spaceName = ""
        localName = name # <classes>.<name>
        for namespace in sorted(namespaces, key=len, reverse=True):
            if name.startswith(namespace + "."):
                spaceName = namespace
                localName = name.replace(namespace + ".", "")
                break
        pieces = localName.split(".")
        if len(pieces) > 2: # <class>.<class>.<class>.<name>
            return spaceName, ".".join(pieces[:-1]), pieces[-2], pieces[-1]
        elif len(pieces) == 2: # <class>.<name>
            return spaceName, pieces[0], pieces[0], pieces[1]
        elif len(pieces) == 1: # <name>
            return spaceName, "", "", pieces[0]
        else:
            return spaceName, "", "" # error?!

def make_cpp_type(t):
    if(t == "size_t"):
        return t
    return t.replace("_", "::")

class ArgInfo():
    def __init__(self, arg_tuple): # [ ctype, name, def val, [mod], argno ]
        self.pointer = False
        type = arg_tuple[0]
        if type.endswith("*"):
            type = type[:-1]
            self.pointer = True
        if type == "String":
            type = "string"
        if type == "Size2i":
            type = "Size"
        self.ctype = type
        self.type = make_cpp_type(type)
        self.name = arg_tuple[1]
        self.defval = ""
        if len(arg_tuple) > 2:
            self.defval = arg_tuple[2]
        self.out = ""
        if len(arg_tuple) > 3 and "/O" in arg_tuple[3]:
            self.out = "O"
        if len(arg_tuple) > 3 and "/IO" in arg_tuple[3]:
            self.out = "IO"

    def __repr__(self):
        return Template("ARG $ctype$p $name=$defval").substitute(ctype=self.type,
                                                                  p=" *" if self.pointer else "",
                                                                  name=self.name,
                                                                  defval="" #self.defval
                                                                )

class FuncInfo(GeneralInfo):
    def __init__(self, gen, decl, namespaces=[]): # [ funcname, return_ctype, [modifiers], [args] ]
        GeneralInfo.__init__(self, gen, decl[0], namespaces)
        self.isconstructor = self.name == self.classname
        self.overridename = self.name
        for m in decl[2]:
            if m.startswith("="):
                self.overridename = m[1:]
        self.static = ["","static"][ "/S" in decl[2] ]
        if self.isconstructor:
            self.type = "::".join(decl[0].split(".")[1:-1])
        else:
            self.type = make_cpp_type(decl[1])
        if self.type == "Size2i":
            self.type = "Size"
        self.cppname = self.name.replace(".", "::")
        self.cname = "_".join(decl[0].split(".")[1:])
        self.args = []
        self.class_nested_cppname = "::".join(decl[0].split(".")[1:-1])
        for a in decl[3]:
            self.args.append(ArgInfo(a))
        if self.isconstructor:
            self.name = "new"
        self.const = "/C" in decl[2]

        # register self to class or generator
        if self.class_nested_cppname == "":
            gen.functions.append(self)
        elif gen.is_ignored(self.class_nested_cppname):
            logging.info('ignored: %s', self)
        elif self.class_nested_cppname in ManualFuncs:
            logging.info('manual: %s', self)
        elif gen.is_ignored(self.class_nested_cppname):
            pass
        else:
            self.ci = gen.get_class(self.class_nested_cppname)
            self.ci.add_method(self)

    def __repr__(self):
        return Template("FUNC <$type $namespace.$classpath.$name $args>").substitute(**self.__dict__)

class ClassPropInfo():
    def __init__(self, decl): # [f_ctype, f_name, '', '/RW']
        self.ctype = decl[0]
        self.name = decl[1]
        self.rw = "/RW" in decl[3]

    def __repr__(self):
        return Template("PROP $ctype $name").substitute(ctype=self.ctype, name=self.name)

class ClassInfo(GeneralInfo):
    def __init__(self, gen, decl, namespaces=[]): # [ 'class/struct cname', ': base', [modlist] ]
        GeneralInfo.__init__(self, gen, decl[0], namespaces)
        self.methods = []
        self.simple = False
        self.nested = False
        for m in decl[2]:
            if m == "/Simple" or m == "/Map" :
                self.simple = True
        if len(decl[0].split(".")) > 2:
            self.nested = True
        self.nested_cppname = "::".join(decl[0].split(".")[1:])
        self.nested_cname = "_".join(decl[0].split(".")[1:])
        self.base = decl[1].split(" ")[1].split("::")[1] if len(decl)>1 and len(decl[1])>1 else ""

        # class props
        self.props= []
        for p in decl[3]:
            self.props.append( ClassPropInfo(p) )

        # register
        if not gen.is_ignored(self.nested_cppname):
            gen.classes[self.nested_cppname] = self

    def __repr__(self):
#        return Template("CLASS $namespace.$classpath.$name : $base").substitute(**self.__dict__)
        return Template("CLASS $namespace.$classpath.$name").substitute(**self.__dict__)

    def add_method(self, fi):
        self.methods.append(fi)

    def getAllMethods(self):
        result = []
        result.extend([fi for fi in sorted(self.methods) if fi.isconstructor])
        result.extend([fi for fi in sorted(self.methods) if not fi.isconstructor])
        return result

class ConstInfo(GeneralInfo):
    def __init__(self, gen, decl, addedManually=False, namespaces=[]):
        GeneralInfo.__init__(self, gen, decl[0], namespaces)
        self.fullname = decl[0].split(" ")[1]
        if len(self.fullname.split(".")) > 1:
            self.rustname = "_".join(self.fullname.split(".")[1:])
        else:
            self.rustname = self.fullname
        self.cname = self.name.replace(".", "::")
        self.value = decl[1]
        self.addedManually = addedManually

        # register
        if self.isIgnored():
            logging.info('ignored: %s', self)
        elif not gen.get_const(self.name):
            gen.consts.append(self)

    def __repr__(self):
        return Template("CONST $name=$value$manual").substitute(name=self.name,
                                                                 value=self.value,
                                                                 manual="(manual)" if self.addedManually else "")

    def isIgnored(self):
        for c in const_ignore_list:
            if re.match(c, self.name):
                return True
        return False

    def gen_rust(self):
        io = StringIO()
        io.write("// %s [%s] [%s] [%s]\n"%(self.fullname, self.cname, self.value, self.rustname))
        if self.value.startswith('"'):
            io.write("pub const %s:&'static str = %s;\n"%(self.rustname, self.value))
        elif re.match("^(-?[0-9]+|0x[0-9A-F]+)$", self.value):
            io.write("pub const %s:i32 = %s;\n"%(self.rustname, self.value))
        return io.getvalue()

    def gen_cpp_for_complex(self):
        # only use C-constant dumping for unnested const
        if len(self.fullname.split(".")) > 2:
            return ""
        else:
            return """    printf("pub const %s:i32 = 0x%%x;\\n", %s);\n"""%(self.rustname, self.name)

#
#       GENERATOR
#

class RustWrapperGenerator(object):
    def __init__(self):
        self.clear()

    def clear(self):
        self.module = ""
        self.Module = ""
        self.classes = { }
        self.functions = [];
        self.ported_func_list = []
        self.skipped_func_list = []
        self.def_args_hist = {} # { def_args_cnt : funcs_cnt }
        self.consts = []

    def get_class(self, classname):
        return self.classes[classname] # or self.Module]

    def get_const(self, name):
        for c in self.consts:
            if c.cname == name:
                return c
        return None

    def add_decl(self, decl):
        name = decl[0]
        if name.startswith("struct") or name.startswith("class"):
            ClassInfo(self, decl, namespaces=self.namespaces)
        elif name.startswith("const"):
            ConstInfo(self, decl, namespaces=self.namespaces)
        else:
            FuncInfo(self, decl, namespaces=self.namespaces)

    def gen(self, srcfiles, module, output_path):
        parser = hdr_parser.CppHeaderParser()
        self.output_path = output_path
        self.module = module
        self.Module = module.capitalize()
        includes = [];

        for hdr in srcfiles:
            decls = parser.parse(hdr)
            self.namespaces = parser.namespaces
            logging.info("\n\n===== Header: %s =====", hdr)
            logging.info("Namespaces: %s", parser.namespaces)
            if decls:
                includes.append('#include "' + hdr + '"')
            for decl in decls:
                logging.info("\n--- Incoming ---\n%s", pformat(decl, 4))
                self.add_decl(decl)

        if module in ManualFuncs:
            for decl in ManualFuncs[self.module]:
                logging.info("\n--- Manual ---\n%s", pformat(decl, 4))
                self.add_decl(decl)

        logging.info("\n\n===== Generating... =====")
        self.moduleCppTypes = StringIO()
        self.moduleCppCode = StringIO()
        self.moduleCppConsts = StringIO()
        self.moduleRustCode = StringIO()
        self.moduleRustExterns = StringIO()

        for co in self.consts:
            rust = co.gen_rust()
            if rust:
                self.moduleRustCode.write(rust)
            else:
                self.moduleCppConsts.write(co.gen_cpp_for_complex())

        if self.moduleCppConsts.getvalue != "":
            self.moduleRustCode.write(
                """include!(concat!(env!("OUT_DIR"), "/%s.consts.rs"));\n"""%(self.module)
            )

        for ci in self.classes.values():
            if ci.nested:
                self.gen_nested_class_decl(ci)

        for c in value_struct_types:
            if c[0] == module:
                self.gen_value_struct(c)

        for c in self.classes.values():
            if c.simple:
                self.gen_simple_class(c)

        for fi in self.functions:
            self.gen_func(None, fi)

        if module in forced_boxed_classes:
            for cb in forced_boxed_classes[module]:
                self.gen_boxed_class(cb)

        for ci in self.classes.values():
            self.gen_class(ci)

        with open(output_path+"/types.h", "a") as f:
            f.write(self.moduleCppTypes.getvalue())

        with open(output_path+"/" + self.module + ".consts.cpp", "w") as f:
            f.write("""#include <cstdio>\n""")
            f.write("""#include "opencv2/opencv_modules.hpp"\n""")
            f.write("""#include "opencv2/%s/%s.hpp"\n"""%(module,module))
            f.write("""using namespace cv;\n""")
            f.write("int main(int argc, char**argv) {\n");
            f.write(self.moduleCppConsts.getvalue())
            f.write("}\n");

        with open(output_path+"/"+module+".cpp", "w") as f:
            f.write(Template(T_CPP_MODULE).substitute(m = module, M = module.upper(), code = self.moduleCppCode.getvalue(), includes = "\n".join(includes)))

        with open(output_path+"/%s.externs.rs"%(module), "w") as f:
            f.write("extern \"C\" {\n")
            f.write(self.moduleRustExterns.getvalue())
            f.write("}\n")

        with open(output_path+"/"+module+".rs", "w") as f:
            f.write(Template(T_RUST_MODULE).substitute(m = module, M = module.upper(), code = self.moduleRustCode.getvalue(), module_import = ("use ::sys::core::*;\n" if not module == "core" else "")))

        with open(output_path+"/"+module+".txt", "w") as f:
            f.write(self.makeReport())

    def makeReport(self):
        '''
        Returns string with generator report
        '''
        report = StringIO()
        total_count = len(self.ported_func_list)+ len(self.skipped_func_list)
        report.write("PORTED FUNCs LIST (%i of %i):\n\n" % (len(self.ported_func_list), total_count))
        report.write("\n".join(self.ported_func_list))
        report.write("\n\nSKIPPED FUNCs LIST (%i of %i):\n\n" % (len(self.skipped_func_list), total_count))
        report.write("".join(self.skipped_func_list))
        for i in self.def_args_hist.keys():
            report.write("\n%i def args - %i funcs" % (i, self.def_args_hist[i]))
        return report.getvalue()

    def is_string(self, type_name):
        return type_name == "string"

    def is_primitive(self, type_name):
        return type_name in primitives

    # opencv classes with the /Simple modifiers
    def is_simple(self, type_name):
        return type_name in self.classes and self.classes[type_name].simple

    # special types from core, passed by value
    def is_value(self, type_name):
        for k in value_struct_types:
            if k[1] == type_name:
                return True
        return self.is_simple(type_name)

    def is_ptr(self, type_name):
        return type_name.startswith("Ptr::")

    def is_vector_of_vector(self, type_name):
        return type_name.startswith("vector::vector::")

    def is_vector(self, type_name):
        return type_name.startswith("vector::") and not self.is_vector_of_vector(type_name)

    def is_ignored(self, type_name):
        return type_name.split("::")[-1] in class_ignore_list

    def is_boxed(self, type_name):
        return not (self.is_value(type_name) or self.is_simple(type_name)
            or self.is_primitive(type_name) or self.is_string(type_name))

    def is_trait(self, ci):
        if self.is_value(ci.name):
            return False
        for fi in sorted(ci.methods):
            if fi.isconstructor:
                return False
        return True


    def map_type(self, type_name):
        if self.is_value(type_name):
            return {    "ctype"  : "cv_struct_%s"%(type_name.replace("::","_")),
                        "cpptype": type_name,
                        "rtype"  : "%s"%(type_name.replace("::", "_")) }
        elif self.is_simple(type_name):
            return {    "ctype" : "cv_struct_%s"%(type_name.replace("::","_")),
                        "cpptype": type_name,
                        "rtype" : "%s"%(type_name.replace("::", "_")),
                    }
        elif self.is_primitive(type_name):
            primitives[type_name]["cpptype"] = type_name
            return primitives[type_name]
        elif self.is_vector(type_name):
            h = {       "ctype" : "void*",
                        "cpptype": "vector<%s>"%(type_name.split("::")[-1]),
                        "rctype" : "*mut c_void",
                        "rtype" : "VectorOf%s"%(type_name.split("::")[1]) }
            self.gen_template_wrapper_rust_struct(h)
            return h
        elif self.is_vector_of_vector(type_name):
            h = {    "ctype" : "void*",
                        "rctype" : "*mut c_void",
                        "cpptype": "vector< vector<%s> >"%(type_name.split("::")[-1]),
                        "rtype" : "VectorOfVectorOf%s"%(type_name.split("::")[2]) }
            self.gen_template_wrapper_rust_struct(h)
            return h
        elif self.is_ptr(type_name):
            h = {    "ctype" : "void*",
                        "rctype" : "*mut c_void",
                        "cpptype": "Ptr<%s>"%(type_name.split("::")[-1]),
                        "rtype" : "PtrOf%s"%(type_name.split("::")[1]) }
            self.gen_template_wrapper_rust_struct(h)
            return h
        elif self.is_string(type_name):
            return { "ctype" : "const char*", "cpptype" : "string",
                "rtype": "*const ::libc::types::os::arch::c95::c_char",
                "rrvtype": "String" }
        else:
            return { "ctype" : "void*", "cpptype" : type_name, "rctype": "*mut c_void", "rtype": "%s"%(type_name) }

    def gen_vector_struct_for(self, name):
        struct_name = "cv_vector_of_"+name
        self.defined_in_types_h.appand(struct_name)
        self.moduleCppTypes.write

    def gen_func(self, ci, fi, mode="define"):
        if fi.isconstructor:
            rv_type = ci.nested_cppname
        else:
            rv_type = fi.type;
        if fi.overridename == "operator ()":
            msg = "can not map operator () yet"
            self.skipped_func_list.append("%s\n   %s\n"%(fi,msg))
            return

        for a in fi.args:
            if self.is_ignored(a.type):
                msg = "can not map type %s yet"%(a.type)
                self.skipped_func_list.append("%s\n   %s\n"%(fi,msg))
                return

        rv = self.map_type(rv_type)

        self.ported_func_list.append(fi.__repr__())

        self.moduleCppCode.write("// %s %s %s\n"%(fi.cppname,
            "(constructor)" if fi.isconstructor else "(method)",
            "(const)" if fi.const else "(mut)"))
        self.moduleCppCode.write("// %s\n"%(fi))
        self.moduleCppCode.write("// Return value: %s\n"%(rv))

        decl_c_args = "\n        "
        call_cpp_args = ""
        decl_rust_extern_args = ""
        decl_rust_args = ""
        call_rust_args = ""
        rust_args_default_doc = ""
        suffix = "_" if len(fi.args) > 0 else ""
        if not ci == None and not fi.isconstructor:
            decl_c_args += self.map_type(ci.name)["ctype"] + " instance"
            if fi.const:
                decl_rust_extern_args = "instance: *const c_void"
                decl_rust_args = "&self"
            else:
                decl_rust_extern_args = "instance: *mut c_void"
                decl_rust_args = "&mut self"
            call_rust_args = "self.as_ptr()"
        for a in fi.args:
            atype = self.map_type(a.type)
            if not decl_c_args.strip() == "":
                decl_c_args+=",\n        "
            if not call_cpp_args == "":
                call_cpp_args += ", "
            if not decl_rust_extern_args == "":
                decl_rust_extern_args += ", "
                decl_rust_args += ", "
                call_rust_args += ", "
            suffix += a.type[0].capitalize()

            rsname = a.name
            if rsname in ["type","box"]:
                rsname = "_" + rsname

            if a.defval != "":
                rust_args_default_doc += \
                    "  /// * %s: default %s\n"%(rsname, a.defval)

            rw = a.out == "O" or a.out == "IO"

            decl_c_args += "/* "
            decl_c_args += a.__repr__() + "\n        "
            decl_c_args += atype.__repr__() + "\n        "
            if a.type in self.classes:
                decl_c_args += "%s\n        "%(self.classes[a.type])
            else:
                decl_c_args += "%s is not a class of this module\n        "%(a.type)
            if rw:
                decl_c_args += "rw "
            if self.is_boxed(a.type):
                decl_c_args += "boxed "
            if self.is_simple(a.type):
                decl_c_args += "simple "
            decl_c_args += "\n        */ "

            arg_decl_star = not self.is_boxed(a.type) and rw
            if self.is_string(a.type):
                decl_c_args += "const char *" + a.name
            elif arg_decl_star:
                decl_c_args += atype["ctype"] + " *" + a.name
            else:
                decl_c_args += atype["ctype"] + " " + a.name

            if self.is_string(a.type):
                decl_rust_args += "%s:&str"%(rsname)
            elif self.is_primitive(a.type) or self.is_value(a.type) \
                    or self.is_simple(a.type):
                decl_rust_args += rsname + ":" + atype["rtype"]
            elif rw:
                decl_rust_args += rsname + ":&mut " + atype["rtype"]
            else:
                decl_rust_args += rsname + ":& " + atype["rtype"]

            if self.is_boxed(a.type) or self.is_vector(a.type) \
                    or self.is_vector_of_vector(a.type) or self.is_ptr(a.type):
                call_rust_args += "%s.ptr"%(rsname)
            elif self.is_string(a.type):
                call_rust_args += "CString::new(%s).unwrap().as_ptr()"%(rsname)
            else:
                call_rust_args += "%s"%(rsname)

            if self.is_boxed(a.type) or self.is_vector(a.type) \
                    or self.is_vector_of_vector(a.type) or self.is_ptr(a.type):
                call_cpp_args += "*((%s*)%s)"%(atype["cpptype"], a.name)
            elif a.type == "string":
                call_cpp_args += a.name
            elif "arg_c_to_cpp" in atype:
                call_cpp_args += atype["arg_c_to_cpp"].substitute(src=a.name)
            elif self.is_value(a.type) or (a.type in self.classes and self.classes[a.type].simple):
                if arg_decl_star and a.pointer:
                    call_cpp_args += "reinterpret_cast<" + atype["cpptype"] + "*>(" +  a.name + ")"
                elif arg_decl_star and not a.pointer:
                    call_cpp_args += "*reinterpret_cast<" + atype["cpptype"] + "*>(" +  a.name + ")"
                elif a.pointer:
                    call_cpp_args += "reinterpret_cast<" + atype["cpptype"] + "*>(&" +  a.name + ")"
                else:
                    call_cpp_args += "*reinterpret_cast<" + atype["cpptype"] + "*>(&" +  a.name + ")"
            else:
                if arg_decl_star and a.pointer:
                    call_cpp_args += a.name
                elif not arg_decl_star and not a.pointer:
                    call_cpp_args += a.name
                else:
                    call_cpp_args += "*" + a.name

            decl_rust_extern_args += rsname + ": " + (atype.get("rctype") or atype["rtype"])

        if ci == None:
            c_name = "cv_%s_%s%s"%(module, fi.overridename, suffix);
        else:
            c_name = "cv_%s_%s_%s%s"%(module, ci.nested_cname, fi.overridename, suffix);

        # C function prototype
        self.moduleCppCode.write("struct cv_return_value_%s %s(%s) {\n"%(rv["ctype"].replace(" ","_").replace(":","_").replace(" ","_").replace("*", "_"), c_name, decl_c_args));

        self.moduleCppCode.write("  try {\n");
        # cpp method call with prefix
        if ci == None:
            call_name = "cv::" + fi.cppname
        elif fi.isconstructor and self.is_boxed(ci.name):
            call_name = ci.nested_cppname
        elif fi.cppname == "()":
            call_name = "(*((%s*) instance))"%(self.map_type(ci.name)["cpptype"])
        else:
            call_name = "((%s*) instance)->%s"%(self.map_type(ci.name)["cpptype"], fi.cppname)

        # actual call
        if fi.type == "void":
            self.moduleCppCode.write("  %s(%s);\n"%(call_name, call_cpp_args))
#        elif self.is_ptr(rv_type):
#            self.moduleCppCode.write("  %s cpp_return_value = %s(%s);\n"%(rv["cpptype"], call_cpp_args));
        elif fi.isconstructor and self.is_boxed(rv_type):
            self.moduleCppCode.write("  %s* cpp_return_value = new %s(%s);\n"%(rv["cpptype"], call_name,
                call_cpp_args));
        elif fi.isconstructor and call_cpp_args != "":
            self.moduleCppCode.write("  %s cpp_return_value(%s);\n"%(rv["cpptype"], call_cpp_args));
        elif fi.isconstructor:
            self.moduleCppCode.write("  %s cpp_return_value;\n"%(rv["cpptype"]));
        else:
            self.moduleCppCode.write("  %s cpp_return_value = %s(%s);\n"%(rv["cpptype"], call_name,
                call_cpp_args));

        self.gen_c_return_value_type(rv);

        # return value
        if fi.type == "void":
            self.moduleCppCode.write("  return { NULL, 0 };\n");
        elif self.is_string(rv_type):
            self.moduleCppCode.write("  return { NULL, strdup(cpp_return_value.c_str()) };");
        elif self.is_boxed(rv_type) and not fi.isconstructor:
            self.moduleCppCode.write("  return { NULL, new %s(cpp_return_value) };\n"%(rv["cpptype"]));
        elif self.is_boxed(rv_type) and fi.isconstructor:
            self.moduleCppCode.write("  return { NULL, cpp_return_value };\n")
        elif self.is_value(rv_type):
            self.moduleCppCode.write("  return { NULL, *reinterpret_cast<cv_struct_%s*>(&cpp_return_value) };\n"%(rv_type.replace("::", "_")))
        elif self.is_vector(rv_type):
            self.moduleCppCode.write("  return { NULL, (void*) new %s(cpp_return_value) };\n"%(rv["cpptype"]));
        elif "return_cpp_to_c" in rv:
            self.moduleCppCode.write(rv["return_cpp_to_c"].substitute(src="cpp_return_value"));
        else:
            self.moduleCppCode.write("  return { NULL, cpp_return_value };\n");

        self.moduleCppCode.write("} catch (cv::Exception& e) {\n");
        self.moduleCppCode.write("    char* msg = strdup(e.what());\n");
        self.moduleCppCode.write("    return { msg, 0 };\n");
        self.moduleCppCode.write("} catch (...) {\n");
        self.moduleCppCode.write("    char* msg = strdup(\"unspecified error in OpenCV guts\");\n");
        self.moduleCppCode.write("    return { msg, 0 };\n");
        self.moduleCppCode.write("}\n");

        self.moduleCppCode.write("}\n\n");

        rust_extern_rs = "rv::cv_return_value_%s"%(rv["ctype"].replace("*","_").replace(" ","_").replace(":","_"))

        # rust's extern C
        if mode == "define" or mode == "trait": 
            self.moduleRustExterns.write("pub fn %s(%s) -> %s;\n"%(c_name, decl_rust_extern_args, rust_extern_rs))

        rname = renamed_funcs.get(c_name) or ("new" if fi.isconstructor else fi.overridename)

        # rust safe wrapper
        self.moduleRustCode.write(rust_args_default_doc);
        pub = "pub" if mode != "trait" else ""
#        if mode == "decl":
#            self.moduleRustCode.write("  fn %s(%s) -> Result<%s,String>;\n"%(rname,
#                    decl_rust_args, rv.get("rrvtype") or rv.get("rtype")));
#        else:
        self.moduleRustCode.write("  %s fn %s(%s) -> Result<%s,String> {\n"%(pub, rname,
                decl_rust_args, rv.get("rrvtype") or rv.get("rtype")))
        self.moduleRustCode.write("    unsafe {\n")
        self.moduleRustCode.write("      let rv = ::%s(%s);\n"%(c_name, call_rust_args))
        self.moduleRustCode.write("      if rv.error_msg as i32 != 0i32 {\n")
        self.moduleRustCode.write("          let v = CStr::from_ptr(rv.error_msg).to_bytes().to_vec();\n");
        self.moduleRustCode.write("          ::libc::free(rv.error_msg as *mut c_void);\n")
        self.moduleRustCode.write("          return Err(String::from_utf8(v).unwrap())\n")
        self.moduleRustCode.write("      }\n");
        if fi.type == "void":
            self.moduleRustCode.write("      Ok(())\n");
        elif(self.is_string(rv_type)):
            self.moduleRustCode.write("      let v = CStr::from_ptr(rv.result).to_bytes().to_vec();\n");
            self.moduleRustCode.write("      ::libc::free(rv.result as *mut c_void);\n");
            self.moduleRustCode.write("      Ok(String::from_utf8(v).unwrap())\n");
        elif self.is_boxed(rv_type):
            self.moduleRustCode.write("      Ok(%s{ ptr: rv.result })\n"%(rv["rtype"], ))
        elif fi.type == "bool":
            self.moduleRustCode.write("      Ok(rv.result!=0)\n")
        else:
            self.moduleRustCode.write("      Ok(rv.result)\n")
        self.moduleRustCode.write("    }\n");
        self.moduleRustCode.write("  }\n")

    def gen_value_struct_field(self, name, typ):
        rsname = name
        if rsname in ["box", "type"]:
            rsname = "_" + rsname
        if "[" in typ:
            bracket = typ.index("[")
            cppt = typ[:bracket]
            ct = self.map_type(cppt)["ctype"]
            size = typ[bracket+1:-1]
            rst = self.map_type(cppt)["rtype"]
            self.moduleCppTypes.write("    %s %s[%s];\n"%(ct, name, size))
            self.moduleRustCode.write("    pub %s: [%s;%s],\n"%(rsname, rst, size))
        else:
            cppt = typ
            ct = self.map_type(cppt)["ctype"]
            rst = self.map_type(cppt)["rtype"]
            self.moduleCppTypes.write("    %s %s;\n"%(ct, name))
            self.moduleRustCode.write("    pub %s: %s,\n"%(rsname, rst))

    def gen_value_struct(self, c):
        self.moduleCppTypes.write("typedef struct cv_struct_%s {\n"%(c[1]))
        self.moduleRustCode.write("#[repr(C)]#[derive(Debug,PartialEq)] pub struct %s {\n"%(c[1]))
        for field in value_struct_types[c]:
            self.gen_value_struct_field(field[0], field[1])
        self.moduleCppTypes.write("} cv_struct_%s;\n\n"%(c[1]))
        self.moduleRustCode.write("}\n")

    def gen_simple_class(self,ci):
        self.moduleCppTypes.write("typedef struct cv_struct_%s {\n"%(ci.nested_cname))
        self.moduleRustCode.write("#[repr(C)]#[derive(Debug,PartialEq)] pub struct %s {\n"%(ci.nested_cname))
        for p in ci.props:
            self.gen_value_struct_field(p.name, p.ctype)
        self.moduleRustCode.write("}\n")
        self.moduleCppTypes.write("} cv_struct_%s;\n\n"%(ci.nested_cname))

    def gen_template_wrapper_rust_struct(self, typ):
        rtype = typ["rtype"]
        with open(self.output_path+"/"+typ["rtype"]+".type.rs", "w") as f:
            f.write("#[allow(dead_code)] pub struct %s { pub ptr: *mut c_void }\n"%(rtype));
            if rtype.startswith("VectorOf"):
                f.write(Template("""
                    extern "C" {
                        fn cv_new_$rtype() -> *mut c_void;
                        fn cv_delete_$rtype(ptr:*mut c_void) -> ();
                        fn cv_${rtype}_len(ptr:*mut c_void) -> i32;
                    }
                    impl $rtype {
                        pub fn new() -> $rtype {
                            unsafe { return $rtype { ptr:cv_new_$rtype() } };
                        }
                        pub fn len(&self) -> i32 {
                            unsafe { return cv_${rtype}_len(self.ptr); }
                        }
                    }
                    impl Drop for $rtype {
                        fn drop(&mut self) {
                            unsafe { cv_delete_$rtype(self.ptr) };
                        }
                    }\n""").substitute(rtype=rtype))
        if rtype.startswith("VectorOf"):
            with open(self.output_path+"/"+typ["rtype"]+".type.cpp", "w") as f:
                f.write(Template("""
                    #include "opencv2/opencv_modules.hpp"
                    #include "opencv2/$module/$module.hpp"
                    using namespace cv;
                    extern "C" { 
                        void* cv_new_$rtype() { return new std::$cpptype(); }
                        void cv_delete_$rtype(void* ptr) { delete (($cpptype*) ptr); }
                        int cv_${rtype}_len(void* ptr) { return (($cpptype*) ptr)->size(); }
                    }\n""").substitute(
                rtype=rtype, cpptype=typ["cpptype"], module=self.module))

    def gen_c_return_value_type(self, typ):
        with open(self.output_path+"/cv_return_value_"+typ["ctype"].replace("*","_").replace(" ","_").replace(":","_")+".type.h", "w") as f:
            f.write(Template("""struct cv_return_value_$sane {
               char* error_msg;
               $ctype result;
            };\n""").substitute(
                sane=typ["ctype"].replace("*","_").replace(" ","_").replace(":","_"),
                ctype="int" if typ["ctype"] == "void" else typ["ctype"]
            ))
        with open(self.output_path+"/cv_return_value_"+typ["ctype"].replace("*","_").replace(" ","_").replace(":","_")+".rv.rs", "w") as f:
            f.write(Template("""#[repr(C)] pub struct cv_return_value_$sane {
               pub error_msg: *const ::libc::types::os::arch::c95::c_char,
               pub result: $rtype
            }\n""").substitute(
                sane=typ["ctype"].replace("*","_").replace(" ","_").replace(":","_"),
                rtype=typ.get("rctype") or typ["rtype"]
            ))

    def gen_boxed_class(self, name):
        cname = name
        cppname = name
        if name in self.classes:
            cname = self.classes[name].nested_cname
            cppname = self.classes[name].nested_cppname
        self.moduleRustExterns.write("pub fn cv_%s_delete_%s(ptr : *mut c_void);\n"%(self.module,cname));

        self.moduleRustCode.write(Template("""
            #[allow(dead_code)]
            pub struct $cname {
                pub ptr: *mut c_void 
            }
            impl Drop for $cname {
                fn drop(&mut self) {
                    unsafe { ::cv_${module}_delete_${cname}(self.ptr) };
                }
            }
            impl $cname {
                fn as_ptr(&self) -> *mut c_void { self.ptr }
            }
        """).substitute(cname=cname, module=self.module))
        ci = self.get_class(name)
        if ci.base:
            self.moduleRustCode.write(Template("""
                impl $base for $cname {
                    fn as_ptr(&self) -> *mut c_void { self.ptr }
                }
        """).substitute(cname=cname, base=ci.base))
        self.moduleCppCode.write("void cv_%s_delete_%s(void* instance) {\n"%(self.module, cname));
        self.moduleCppCode.write("  delete (cv::%s*) instance;\n"%(cppname));
        self.moduleCppCode.write("}\n");

    def gen_nested_class_decl(self, ci):
        pass
        #self.moduleCppCode.write("class %s;\n"%(ci.nested_cname));

    def gen_class(self, ci):
        if self.is_trait(ci):
            self.moduleRustCode.write("pub trait %s {\n"%(ci.name))
            self.moduleRustCode.write("  fn as_ptr(&self) -> *mut c_void;\n")
            for fi in ci.getAllMethods():
                self.gen_func(ci, fi, "trait")
            self.moduleRustCode.write("} // trait %s\n"%(ci.name))
        else:
            if self.is_boxed(ci.nested_cppname):
                self.gen_boxed_class(ci.nested_cppname)
            self.moduleRustCode.write("impl %s {\n"%(ci.name))
            for fi in ci.getAllMethods():
                self.gen_func(ci, fi)
            self.moduleRustCode.write("}\n");

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage:\n", \
            os.path.basename(sys.argv[0]), \
            "<full path to hdr_parser.py> <out_dir> <module name> <C++ header> [<C++ header>...]")
        print("Current args are: ", ", ".join(["'"+a+"'" for a in sys.argv]))
        exit(0)

    hdr_parser_path = os.path.abspath(sys.argv[1])
    if hdr_parser_path.endswith(".py"):
        hdr_parser_path = os.path.dirname(hdr_parser_path)
    sys.path.append(hdr_parser_path)
    import hdr_parser
    dstdir = sys.argv[2]
    module = sys.argv[3]
    srcfiles = sys.argv[4:]
    logging.basicConfig(filename='%s/%s.log' % (dstdir, module), format=None, filemode='w', level=logging.INFO)
    handler = logging.StreamHandler()
    handler.setLevel(logging.WARNING)
    logging.getLogger().addHandler(handler)
    print("Generating module '" + module + "' from headers:\n\t" + "\n\t".join(srcfiles))
    generator = RustWrapperGenerator()
    generator.gen(srcfiles, module, dstdir)

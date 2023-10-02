use IO;
use ArkoudaCTypesCompat;
use ArkoudaStringBytesCompat;

require "../src/ArrowFunctions.h";
require "../src/ArrowFunctions.o";

proc getVersionInfo() {
  extern proc c_getVersionInfo(): c_string_ptr;
  extern proc strlen(str): c_int;
  extern proc c_free_string(ptr);
  var cVersionString = c_getVersionInfo();
  defer {
    c_free_string(cVersionString: c_ptr_void);
  }
  var ret: string;
  try {
    ret = string.createCopyingBuffer(cVersionString,
                              strlen(cVersionString));
  } catch e {
    ret = "Error converting Arrow version message to Chapel string";
  }
  return ret;
}

proc main() {
  var ArrowVersion = getVersionInfo();
  writeln("Found Arrow version: ", ArrowVersion);
  return 0;
}

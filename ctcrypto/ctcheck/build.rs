fn main() {
    println!("cargo:rerun-if-changed=src/shim.c");
    cc::Build::new().file("src/shim.c").opt_level(1).compile("ctshim");
}

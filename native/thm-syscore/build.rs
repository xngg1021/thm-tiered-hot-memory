use std::{env, path::PathBuf, process::Command};

fn main() {
    println!("cargo:rerun-if-changed=native_io.c");
    if env::var_os("CARGO_FEATURE_NATIVE_IO").is_none() { return; }
    let out = PathBuf::from(env::var_os("OUT_DIR").unwrap());
    let windows = env::var("CARGO_CFG_TARGET_OS").unwrap() == "windows";
    if windows {
        let object = out.join("thm_io.obj");
        assert!(Command::new("cl").args(["/nologo", "/c", "native_io.c"])
            .arg(format!("/Fo{}", object.display())).status().unwrap().success());
        assert!(Command::new("lib").arg("/nologo").arg(format!("/OUT:{}", out.join("thm_io.lib").display()))
            .arg(&object).status().unwrap().success());
    } else {
        let object = out.join("thm_io.o");
        assert!(Command::new("cc").args(["-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-c", "native_io.c", "-o"])
            .arg(&object).status().unwrap().success());
        assert!(Command::new("ar").arg("crs").arg(out.join("libthm_io.a")).arg(object).status().unwrap().success());
    }
    println!("cargo:rustc-link-search=native={}", out.display());
    println!("cargo:rustc-link-lib=static=thm_io");
}

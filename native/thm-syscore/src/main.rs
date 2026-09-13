//! One bounded request per owned process. No dependencies, plugins or networking.
use std::io::{self, Read, Write};
const MAX: usize = 1_048_576;

fn process(request: &[u8]) -> Result<Vec<u8>, String> {
    if request.len() < 2 || request[0] != 1 { return Err("protocol-version".into()); }
    match request[1] {
        0 => Ok(format!("{{\"schema\":\"thm-syscore/1\",\"max_bytes\":{},\"os\":\"{}\",\"native_io\":{},\"owned_process\":true}}",
                        MAX, std::env::consts::OS, cfg!(feature="native-io")).into_bytes()),
        1 | 2 => {
            if request.len() > 4098 { return Err("path-bound".into()); }
            let path = std::str::from_utf8(&request[2..]).map_err(|_| "utf8-path")?;
            if path.is_empty() || path.contains('\0') { return Err("invalid-path".into()); }
            if request[1] == 2 {
                #[cfg(feature="native-io")]
                {
                    use std::ffi::CString;
                    extern "C" { fn thm_native_read(path: *const std::ffi::c_char, data: *mut u8, capacity: usize) -> i64; }
                    let name = CString::new(path).map_err(|_| "invalid-path")?;
                    let mut bytes = vec![0u8; MAX+1];
                    let n = unsafe { thm_native_read(name.as_ptr(), bytes.as_mut_ptr(), bytes.len()) };
                    if n < 0 { return Err(format!("native-io-unavailable:{}", n)); }
                    if n as usize > MAX { return Err("output-bound".into()); }
                    bytes.truncate(n as usize);
                    return Ok(bytes);
                }
                #[cfg(not(feature="native-io"))]
                return Err("native-io-feature-unavailable".into());
            }
            let file = std::fs::File::open(path).map_err(|e| e.to_string())?;
            if !file.metadata().map_err(|e| e.to_string())?.is_file() { return Err("regular-file-required".into()); }
            let mut data = Vec::new();
            file.take((MAX+1) as u64).read_to_end(&mut data).map_err(|e| e.to_string())?;
            if data.len() > MAX { return Err("output-bound".into()); }
            Ok(data)
        },
        _ => Err("unknown-operation".into()),
    }
}

fn main() -> io::Result<()> {
    let mut size = [0u8; 4];
    io::stdin().read_exact(&mut size)?;
    let count = u32::from_le_bytes(size) as usize;
    if count > 4098 { return Err(io::Error::new(io::ErrorKind::InvalidInput, "request-bound")); }
    let mut request = vec![0u8; count];
    io::stdin().read_exact(&mut request)?;
    let (status, payload) = match process(&request) { Ok(v) => (0u8, v), Err(e) => (1u8, e.into_bytes()) };
    let mut out = io::stdout().lock();
    out.write_all(&((payload.len()+1) as u32).to_le_bytes())?;
    out.write_all(&[status])?;
    out.write_all(&payload)?;
    out.flush()
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn protocol_rejects_invalid_frames() {
        for frame in [vec![], vec![2,0], vec![1,255], vec![1,1,0]] { assert!(process(&frame).is_err()); }
    }
    #[test] fn capability_negotiates_without_devices() {
        assert!(String::from_utf8(process(&[1,0]).unwrap()).unwrap().contains("thm-syscore/1"));
    }
    #[test] fn file_identity_bytes_and_bound() {
        let path = std::env::temp_dir().join(format!("thm-syscore-{}", std::process::id()));
        std::fs::write(&path, b"source bytes").unwrap();
        let mut request = vec![1,1]; request.extend(path.to_str().unwrap().as_bytes());
        assert_eq!(process(&request).unwrap(), b"source bytes");
        std::fs::write(&path, vec![0; MAX+1]).unwrap();
        assert!(process(&request).is_err());
        std::fs::remove_file(&path).unwrap();
    }
}

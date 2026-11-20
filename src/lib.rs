use pyo3::prelude::*;

/// A simple Rust function that we will call from KiCad.
/// For the MVP, it just calculates the bounding box of a net's coordinates.
#[pyfunction]
fn calculate_bounding_box(coords: Vec<(f64, f64)>) -> PyResult<(f64, f64, f64, f64)> {
    if coords.is_empty() {
        return Ok((0.0, 0.0, 0.0, 0.0));
    }

    let mut min_x = coords[0].0;
    let mut max_x = coords[0].0;
    let mut min_y = coords[0].1;
    let mut max_y = coords[0].1;

    // Borrow `coords` using `&coords` instead of moving it
    for &(x, y) in &coords {
        if x < min_x {
            min_x = x;
        }
        if x > max_x {
            max_x = x;
        }
        if y < min_y {
            min_y = y;
        }
        if y > max_y {
            max_y = y;
        }
    }

    // `coords` is still valid here!
    println!("Rust: Successfully processed {} coordinates!", coords.len());

    Ok((min_x, min_y, max_x, max_y))
}

#[pymodule]
fn kicad_elmer_engine(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(calculate_bounding_box, m)?)?;
    Ok(())
}

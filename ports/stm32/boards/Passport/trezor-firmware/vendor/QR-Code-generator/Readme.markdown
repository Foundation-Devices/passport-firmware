QR Code generator library
=========================


Introduction
------------

This project aims to be the best, clearest QR Code generator library in multiple languages. The primary goals are flexible options and absolute correctness. Secondary goals are compact implementation size and good documentation comments.

Home page with live JavaScript demo, extensive descriptions, and competitor comparisons: [https://www.nayuki.io/page/qr-code-generator-library](https://www.nayuki.io/page/qr-code-generator-library)


Features
--------

Core features:

* Available in 6 programming languages, all with nearly equal functionality: Java, TypeScript/JavaScript, Python, Rust, C++, C
* Significantly shorter code but more documentation comments compared to competing libraries
* Supports encoding all 40 versions (sizes) and all 4 error correction levels, as per the QR Code Model 2 standard
* Output format: Raw modules/pixels of the QR symbol
* Detects finder-like penalty patterns more accurately than other implementations
* Encodes numeric and special-alphanumeric text in less space than general text
* Open-source code under the permissive MIT License

Manual parameters:

* User can specify minimum and maximum version numbers allowed, then library will automatically choose smallest version in the range that fits the data
* User can specify mask pattern manually, otherwise library will automatically evaluate all 8 masks and select the optimal one
* User can specify absolute error correction level, or allow the library to boost it if it doesn't increase the version number
* User can create a list of data segments manually and add ECI segments

Optional advanced features (Java only):

* Encodes Japanese Unicode text in kanji mode to save a lot of space compared to UTF-8 bytes
* Computes optimal segment mode switching for text with mixed numeric/alphanumeric/general/kanji parts

More information about QR Code technology and this library's design can be found on the project home page.


Examples
--------

Java language:

```java
import java.awt.image.BufferedImage;
import java.io.File;
import java.util.List;
import javax.imageio.ImageIO;
import io.nayuki.qrcodegen.*;

// Simple operation
QrCode qr0 = QrCode.encodeText("Hello, world!", QrCode.Ecc.MEDIUM);
BufferedImage img = toImage(qr0, 4, 10);  // See QrCodeGeneratorDemo
ImageIO.write(img, "png", new File("qr-code.png"));

// Manual operation
List<QrSegment> segs = QrSegment.makeSegments("3141592653589793238462643383");
QrCode qr1 = QrCode.encodeSegments(segs, QrCode.Ecc.HIGH, 5, 5, 2, false);
for (int y = 0; y < qr1.size; y++) {
    for (int x = 0; x < qr1.size; x++) {
        (... paint qr1.getModule(x, y) ...)
    }
}
```

TypeScript/JavaScript languages:

```typescript
// Name abbreviated for the sake of these examples here
const QRC = qrcodegen.QrCode;

// Simple operation
const qr0 = QRC.encodeText("Hello, world!", QRC.Ecc.MEDIUM);
const svg = toSvgString(qr0, 4);  // See qrcodegen-input-demo

// Manual operation
const segs = qrcodegen.QrSegment.makeSegments("3141592653589793238462643383");
const qr1 = QRC.encodeSegments(segs, QRC.Ecc.HIGH, 5, 5, 2, false);
for (let y = 0; y < qr1.size; y++) {
    for (let x = 0; x < qr1.size; x++) {
        (... paint qr1.getModule(x, y) ...)
    }
}
```

Python language:

```python
from qrcodegen import *

# Simple operation
qr0 = QrCode.encode_text("Hello, world!", QrCode.Ecc.MEDIUM)
svg = to_svg_str(qr0, 4)  # See qrcodegen-demo

# Manual operation
segs = QrSegment.make_segments("3141592653589793238462643383")
qr1 = QrCode.encode_segments(segs, QrCode.Ecc.HIGH, 5, 5, 2, False)
for y in range(qr1.get_size()):
    for x in range(qr1.get_size()):
        (... paint qr1.get_module(x, y) ...)
```

C++ language:

```c++
#include <string>
#include <vector>
#include "QrCode.hpp"
using namespace qrcodegen;

// Simple operation
QrCode qr0 = QrCode::encodeText("Hello, world!", QrCode::Ecc::MEDIUM);
std::string svg = toSvgString(qr0, 4);  // See QrCodeGeneratorDemo

// Manual operation
std::vector<QrSegment> segs =
    QrSegment::makeSegments("3141592653589793238462643383");
QrCode qr1 = QrCode::encodeSegments(
    segs, QrCode::Ecc::HIGH, 5, 5, 2, false);
for (int y = 0; y < qr1.getSize(); y++) {
    for (int x = 0; x < qr1.getSize(); x++) {
        (... paint qr1.getModule(x, y) ...)
    }
}
```

C language:

```c
#include <stdbool.h>
#include <stdint.h>
#include "qrcodegen.h"

// Text data
uint8_t qr0[qrcodegen_BUFFER_LEN_MAX];
uint8_t tempBuffer[qrcodegen_BUFFER_LEN_MAX];
bool ok = qrcodegen_encodeText("Hello, world!",
    tempBuffer, qr0, qrcodegen_Ecc_MEDIUM,
    qrcodegen_VERSION_MIN, qrcodegen_VERSION_MAX,
    qrcodegen_Mask_AUTO, true);
if (!ok)
    return;

int size = qrcodegen_getSize(qr0);
for (int y = 0; y < size; y++) {
    for (int x = 0; x < size; x++) {
        (... paint qrcodegen_getModule(qr0, x, y) ...)
    }
}

// Binary data
uint8_t dataAndTemp[qrcodegen_BUFFER_LEN_FOR_VERSION(7)]
    = {0xE3, 0x81, 0x82};
uint8_t qr1[qrcodegen_BUFFER_LEN_FOR_VERSION(7)];
ok = qrcodegen_encodeBinary(dataAndTemp, 3, qr1,
    qrcodegen_Ecc_HIGH, 2, 7, qrcodegen_Mask_4, false);
```

Rust language:

```rust
extern crate qrcodegen;
use qrcodegen::QrCode;
use qrcodegen::QrCodeEcc;
use qrcodegen::QrSegment;

// Simple operation
let qr = QrCode::encode_text("Hello, world!",
    QrCodeEcc::Medium).unwrap();
let svg = to_svg_string(&qr, 4);  // See qrcodegen-demo

// Manual operation
let text: &str = "3141592653589793238462643383";
let segs = QrSegment::make_segments(text);
let qr = QrCode::encode_segments_advanced(&segs, QrCodeEcc::High,
    Version::new(5), Version::new(5), Some(Mask::new(2)), false).unwrap();
for y in 0 .. qr.size() {
    for x in 0 .. qr.size() {
        (... paint qr.get_module(x, y) ...)
    }
}
```


License
-------

Copyright © 2021 Project Nayuki. (MIT License)  
[https://www.nayuki.io/page/qr-code-generator-library](https://www.nayuki.io/page/qr-code-generator-library)

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

* The above copyright notice and this permission notice shall be included in
  all copies or substantial portions of the Software.

* The Software is provided "as is", without warranty of any kind, express or
  implied, including but not limited to the warranties of merchantability,
  fitness for a particular purpose and noninfringement. In no event shall the
  authors or copyright holders be liable for any claim, damages or other
  liability, whether in an action of contract, tort or otherwise, arising from,
  out of or in connection with the Software or the use or other dealings in the
  Software.

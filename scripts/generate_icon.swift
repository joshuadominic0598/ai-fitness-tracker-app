// Render the editable SVG flame as a transparent Mac icon. No emoji font or frame.
import AppKit
let output = CommandLine.arguments[1]
let source = CommandLine.arguments.count > 2 ? CommandLine.arguments[2] : "src/fitness_tracker/web/assets/icon.svg"
let svg = try String(contentsOfFile: source, encoding: .utf8) as NSString
let pathPattern = try NSRegularExpression(pattern: "<path[^>]* d=\"([^\"]+)\"")
let pathMatch = pathPattern.firstMatch(in: svg as String, range: NSRange(location: 0, length: svg.length))!
let data = svg.substring(with: pathMatch.range(at: 1)) as NSString
let pattern = try NSRegularExpression(pattern: "[MCZ]|-?[0-9]+(?:\\.[0-9]+)?")
let tokens = pattern.matches(in: data as String, range: NSRange(location: 0, length: data.length)).map { data.substring(with: $0.range) }
var index = 0
func point() -> NSPoint {
    let x = Double(tokens[index])!, y = Double(tokens[index + 1])!
    index += 2
    return NSPoint(x: x * 8, y: (128 - y) * 8)
}
let path = NSBezierPath()
path.windingRule = .evenOdd
while index < tokens.count {
    let command = tokens[index]; index += 1
    switch command {
    case "M": path.move(to: point())
    case "C":
        let first = point(), second = point(), end = point()
        path.curve(to: end, controlPoint1: first, controlPoint2: second)
    case "Z": path.close()
    default: fatalError("Unsupported SVG path command")
    }
}
let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: 1024, pixelsHigh: 1024, bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: bitmap)
let gradient = NSGradient(colors: [NSColor(srgbRed: 0.21, green: 0.55, blue: 1, alpha: 1), NSColor(srgbRed: 0.45, green: 0.44, blue: 1, alpha: 1), NSColor(srgbRed: 0.68, green: 0.38, blue: 1, alpha: 1)])!
gradient.draw(in: path, angle: 65)
NSGraphicsContext.restoreGraphicsState()
try bitmap.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: output))

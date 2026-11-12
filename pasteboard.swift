import AppKit
import Foundation

let board = NSPasteboard.general
let limit = 20 * 1024 * 1024
var last = board.changeCount
func emit(_ value: [String: Any]) {
    if let data = try? JSONSerialization.data(withJSONObject: value) {
        FileHandle.standardOutput.write(data + Data([10]))
    }
}
func capture() -> [String: Any]? {
    let names = Set((board.types ?? []).map { $0.rawValue })
    if !names.isDisjoint(with: ["org.nspasteboard.ConcealedType", "org.nspasteboard.TransientType"]) { return nil }
    // File references are deliberately excluded: only actual image/text bytes travel.
    if names.contains("public.file-url") { return nil }
    if let bytes = board.data(forType: .png), bytes.count <= limit {
        return ["type": "image", "data": bytes.base64EncodedString()]
    }
    if let tiff = board.data(forType: .tiff), tiff.count <= limit,
       let bitmap = NSBitmapImageRep(data: tiff),
       let png = bitmap.representation(using: .png, properties: [:]), png.count <= limit {
        return ["type": "image", "data": png.base64EncodedString()]
    }
    if let text = board.string(forType: .string), text.utf8.count <= limit {
        return ["type": "text", "data": Data(text.utf8).base64EncodedString()]
    }
    return nil
}
func apply(_ value: [String: Any]) -> Bool {
    guard let type = value["type"] as? String, let b64 = value["data"] as? String,
          let bytes = Data(base64Encoded: b64), bytes.count <= limit else { return false }
    let item = NSPasteboardItem()
    if type == "image" {
        guard let image = NSImage(data: bytes) else { return false }
        item.setData(bytes, forType: .png)
        if let tiff = image.tiffRepresentation { item.setData(tiff, forType: .tiff) }
    } else if type == "text", let text = String(data: bytes, encoding: .utf8) {
        item.setString(text, forType: .string)
    } else { return false }
    item.setString("UUClipboardBridge", forType: NSPasteboard.PasteboardType("org.uucb.origin"))
    board.clearContents()
    let ok = board.writeObjects([item])
    last = board.changeCount
    return ok
}
if CommandLine.arguments.contains("--read") {
    emit(capture() ?? ["type": "empty"])
    exit(0)
}
if CommandLine.arguments.contains("--write") {
    let data = FileHandle.standardInput.readDataToEndOfFile()
    if let v = try? JSONSerialization.jsonObject(with: data) as? [String: Any], apply(v) { exit(0) }
    exit(1)
}
DispatchQueue.global().async {
    while let line = readLine() {
        guard let data = line.data(using: .utf8),
              let v = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { continue }
        DispatchQueue.main.async {
            let ok = apply(v)
            emit(["kind": "ack", "id": v["id"] ?? "", "ok": ok])
        }
    }
    exit(0)
}
let timer = Timer.scheduledTimer(withTimeInterval: 0.35, repeats: true) { _ in
    let now = board.changeCount
    if now != last {
        last = now
        if var v = capture() { v["kind"] = "clipboard"; emit(v) }
    }
}
emit(["kind": "ready"])
RunLoop.main.run()

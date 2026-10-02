// Lists on-screen windows owned by the GECK CrossOver process as JSON (CGWindowID, title, bounds).
import CoreGraphics
import Foundation
let opts: CGWindowListOption = [.optionAll]
guard let info = CGWindowListCopyWindowInfo(opts, kCGNullWindowID) as? [[String: Any]] else { exit(3) }
var out: [[String: Any]] = []
for w in info {
    let owner = w[kCGWindowOwnerName as String] as? String ?? ""
    let title = w[kCGWindowName as String] as? String ?? ""
    guard owner.lowercased().contains("geck") || title.contains("Render Window") || title.contains("camera,") else { continue }
    let b = w[kCGWindowBounds as String] as? [String: Any] ?? [:]
    out.append(["id": w[kCGWindowNumber as String] as? Int ?? 0, "owner": owner, "title": title,
                "layer": w[kCGWindowLayer as String] as? Int ?? 0, "onscreen": w[kCGWindowIsOnscreen as String] as? Bool ?? false,
                "bounds": b])
}
let data = try! JSONSerialization.data(withJSONObject: out, options: [.prettyPrinted, .sortedKeys])
print(String(data: data, encoding: .utf8)!)

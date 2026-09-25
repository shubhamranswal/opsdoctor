import json
import subprocess
import sys

swy = r"C:\Users\shubh\AppData\Local\Programs\swytchcode\bin\swytchcode.exe"

def run_swytchcode(tool_id, args):
    p = subprocess.Popen(
        [swy, "exec", "--json"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    payload = json.dumps({"tool": tool_id, "args": args})
    out, err = p.communicate(payload)
    if p.returncode != 0:
        return None
    s_idx = out.find("{")
    e_idx = out.rfind("}")
    if s_idx != -1 and e_idx != -1:
        try:
            return json.loads(out[s_idx:e_idx+1])
        except Exception:
            return None
    return None

def extract_block_text(b):
    b_type = b.get("type")
    type_obj = b.get(b_type, {})
    if isinstance(type_obj, dict):
        rich_text = type_obj.get("rich_text", [])
        if rich_text:
            return "".join([rt.get("plain_text", "") for rt in rich_text])
        elif "title" in type_obj:
            return type_obj.get("title")
    return ""

def main():
    target_pages = [
        "AcmeFlow Operations",
        "Payment Procedures",
        "Incident Response",
        "Escalation Rules",
        "Refund Policy",
        "Customer Support SOP",
        "Team Ownership"
    ]
    
    # 1. Search
    res = run_swytchcode("notion.search.create", {"body": {}})
    if not res:
        print("Search failed", file=sys.stderr)
        return
        
    items = res.get("data", {}).get("results", [])
    manifest = {
        "workspace": "AcmeFlow Operations",
        "verified_at": "2026-09-26T02:40:00+05:30",
        "pages": {}
    }
    
    for item in items:
        if item.get("object") != "page":
            continue
        props = item.get("properties", {})
        title = ""
        for p_val in props.values():
            if isinstance(p_val, dict) and p_val.get("type") == "title":
                title = "".join([t.get("plain_text", "") for t in p_val.get("title", [])])
                break
        if title in target_pages:
            pid = item.get("id")
            children_res = run_swytchcode("notion.children.get", {"block_id": pid})
            blocks = []
            if children_res:
                raw_blocks = children_res.get("data", {}).get("results", [])
                for rb in raw_blocks:
                    b_type = rb.get("type")
                    text = extract_block_text(rb)
                    blocks.append({"type": b_type, "text": text})
            manifest["pages"][title] = {
                "id": pid,
                "url": item.get("url"),
                "created_time": item.get("created_time"),
                "last_edited_time": item.get("last_edited_time"),
                "blocks": blocks
            }
            
    with open("data/fixtures/notion_pages_manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"Successfully saved manifest with {len(manifest['pages'])} pages.")

if __name__ == "__main__":
    main()

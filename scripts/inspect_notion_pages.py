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
        print(f"Error executing {tool_id}: returncode {p.returncode}", file=sys.stderr)
        print(err, file=sys.stderr)
        return None
    # find JSON object in stdout
    s_idx = out.find("{")
    e_idx = out.rfind("}")
    if s_idx != -1 and e_idx != -1:
        try:
            return json.loads(out[s_idx:e_idx+1])
        except Exception as e:
            print(f"Failed to parse JSON: {e}", file=sys.stderr)
            print(out, file=sys.stderr)
            return None
    print("No JSON found in stdout:", out, file=sys.stderr)
    return None

def main():
    print("--- 1. Searching all Notion items ---")
    res = run_swytchcode("notion.search.create", {"body": {}})
    if not res:
        print("Failed to get search results.")
        return

    data = res.get("data", {})
    results = data.get("results", [])
    print(f"Found {len(results)} items in Notion.")

    pages_found = {}
    for item in results:
        obj_type = item.get("object")
        item_id = item.get("id")
        
        # Extract title
        title = "Untitled"
        if obj_type == "page":
            props = item.get("properties", {})
            title_prop = props.get("title") or props.get("Name") or props.get("title", {})
            # Look through properties for type == 'title'
            for p_name, p_val in props.items():
                if isinstance(p_val, dict) and p_val.get("type") == "title":
                    title_list = p_val.get("title", [])
                    if title_list:
                        title = "".join([t.get("plain_text", "") for t in title_list])
                    break
        elif obj_type == "database":
            title_list = item.get("title", [])
            title = "".join([t.get("plain_text", "") for t in title_list])

        print(f"- [{obj_type}] ID: {item_id} | Title: '{title}'")
        pages_found[title] = {"id": item_id, "object": obj_type}

    print("\n--- 2. Inspecting Blocks for Identified Pages ---")
    for title, meta in pages_found.items():
        page_id = meta["id"]
        print(f"\n================ Page: {title} ({page_id}) ================")
        children_res = run_swytchcode("notion.children.get", {"block_id": page_id})
        if not children_res:
            print(f"  Could not get children for {page_id}")
            continue
        blocks = children_res.get("data", {}).get("results", [])
        print(f"  Total child blocks: {len(blocks)}")
        for b in blocks:
            b_type = b.get("type")
            b_id = b.get("id")
            # Extract plain text depending on block type
            content = ""
            type_obj = b.get(b_type, {})
            if isinstance(type_obj, dict):
                rich_text = type_obj.get("rich_text", [])
                if rich_text:
                    content = "".join([rt.get("plain_text", "") for rt in rich_text])
                elif "title" in type_obj: # e.g. child_page
                    content = f"Child Page Title: {type_obj.get('title')}"
            print(f"  [{b_type}] {content}")

if __name__ == "__main__":
    main()

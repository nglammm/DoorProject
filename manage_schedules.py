#!/usr/bin/env python3
import os
import sys
import json
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCHEDULES_FILE = os.path.join(BASE_DIR, "schedules.json")

VALID_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DAY_ALIASES = {
    "monday": "Mon", "mon": "Mon", "2": "Mon", "t2": "Mon",
    "tuesday": "Tue", "tue": "Tue", "3": "Tue", "t3": "Tue",
    "wednesday": "Wed", "wed": "Wed", "4": "Wed", "t4": "Wed",
    "thursday": "Thu", "thu": "Thu", "5": "Thu", "t5": "Thu",
    "friday": "Fri", "fri": "Fri", "6": "Fri", "t6": "Fri",
    "saturday": "Sat", "sat": "Sat", "7": "Sat", "t7": "Sat",
    "sunday": "Sun", "sun": "Sun", "cn": "Sun", "8": "Sun",
    "*": "*", "all": "*", "everyday": "*", "daily": "*"
}


# --- File I/O (Atomic Save for Live Reload Compatibility) ---

def load_schedules():
    if not os.path.exists(SCHEDULES_FILE):
        return []
    try:
        with open(SCHEDULES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception as e:
        print(f"[ERROR] Could not read '{SCHEDULES_FILE}': {e}")
        return []


def save_schedules(schedules):
    """Writes atomically via a temporary file so the running door script never reads a half-written JSON."""
    tmp_file = SCHEDULES_FILE + ".tmp"
    try:
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(schedules, f, ensure_ascii=False, indent=4)
        os.replace(tmp_file, SCHEDULES_FILE)
        print(f"\n[SAVED] Updated '{SCHEDULES_FILE}' ({len(schedules)} total schedules).")
    except Exception as e:
        print(f"\n[ERROR] Failed to save schedules: {e}")


# --- Input Validation Helpers ---

def prompt_text(prompt_msg, default=None, allow_empty=False):
    suffix = f" [{default}]" if default is not None else ""
    while True:
        val = input(f"{prompt_msg}{suffix}: ").strip()
        if not val and default is not None:
            return default
        if val or allow_empty:
            return val
        print("  -> Value cannot be empty.")


def prompt_time(default=None):
    suffix = f" [{default}]" if default else ""
    while True:
        val = input(f"Enter time in 24h format HH:MM (e.g., 07:30, 18:00){suffix}: ").strip()
        if not val and default:
            return default
        try:
            dt = datetime.strptime(val, "%H:%M")
            return dt.strftime("%H:%M")
        except ValueError:
            print("  -> Invalid time format! Please use HH:MM (00:00 to 23:59).")


def prompt_date(default=""):
    suffix = f" [{default}]" if default else ""
    while True:
        val = input(f"Enter date YYYY-MM-DD (e.g., 2026-10-25){suffix}: ").strip()
        if not val and default:
            return default
        try:
            dt = datetime.strptime(val, "%Y-%m-%d")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            print("  -> Invalid date format! Please use YYYY-MM-DD.")


def prompt_days(default_list=None):
    default_str = ",".join(default_list) if default_list else "*"
    print("\n  Available days: Mon, Tue, Wed, Thu, Fri, Sat, Sun (or '*' for Every Day)")
    print("  Shortcuts: 'weekdays' (Mon-Fri), 'weekend' (Sat-Sun), or Vietnamese 't2,t3,cn'")
    while True:
        raw = input(f"Enter repeating days (comma-separated) [{default_str}]: ").strip().lower()
        if not raw:
            return default_list if default_list else ["*"]

        if raw in ("weekdays", "weekday", "workdays"):
            return ["Mon", "Tue", "Wed", "Thu", "Fri"]
        if raw in ("weekend", "weekends"):
            return ["Sat", "Sun"]

        parts = [p.strip() for p in raw.replace(" ", ",").split(",") if p.strip()]
        parsed_days = []
        invalid = []

        for p in parts:
            if p in DAY_ALIASES:
                mapped = DAY_ALIASES[p]
                if mapped == "*":
                    return ["*"]
                if mapped not in parsed_days:
                    parsed_days.append(mapped)
            else:
                invalid.append(p)

        if invalid:
            print(f"  -> Unrecognized day(s): {', '.join(invalid)}. Try again.")
        elif parsed_days:
            return parsed_days


def prompt_float(prompt_msg, default, min_val=0.5):
    while True:
        val = input(f"{prompt_msg} [{default}]: ").strip()
        if not val:
            return float(default)
        try:
            num = float(val)
            if num >= min_val:
                return int(num) if num.is_integer() else num
            print(f"  -> Value must be at least {min_val} seconds.")
        except ValueError:
            print("  -> Please enter a valid number.")


# --- Display & CRUD Operations ---

def format_schedule_summary(idx, item):
    name = item.get("name", f"Unnamed #{idx}")
    time_str = item.get("time", "??:??")
    action = item.get("action", "say")
    date_str = item.get("date", "")
    days = item.get("days", [])

    if date_str:
        when = f"Date: {date_str} @ {time_str}"
    elif "*" in days or "all" in [d.lower() for d in days]:
        when = f"Every Day @ {time_str}"
    else:
        when = f"{', '.join(days)} @ {time_str}"

    details = []
    if action == "say":
        action_label = "Speak Announcement"
        details.append(f"Text: \"{item.get('text', '')}\"")
    elif action == "unlock_for_everyone":
        action_label = "Guest Mode (Unlock for All Faces)"
        details.append(f"Active Window: {item.get('duration', 3600)}s")
        details.append(f"Actuator: {item.get('actuator_duration', 30)}s")
        details.append(f"Open Wait: {item.get('open_delay', 5)}s")
        if item.get("text"):
            details.append(f"Greeting TTS: \"{item.get('text')}\"")
    elif action == "open_for_duration":
        action_label = "Timed Open & Close"
        details.append(f"Hold Open: {item.get('duration', 60)}s")
        details.append(f"Actuator: {item.get('actuator_duration', 30)}s")
        if item.get("text"):
            details.append(f"TTS: \"{item.get('text')}\"")
    else:
        action_label = action

    detail_str = " | ".join(details)
    return (
        f"  [{idx}] {name}\n"
        f"      When   : {when}\n"
        f"      Action : {action_label}\n"
        f"      Config : {detail_str}"
    )


def list_schedules(schedules):
    print("\n" + "=" * 72)
    print(f" CURRENT SCHEDULES ({len(schedules)} total)")
    print("=" * 72)
    if not schedules:
        print("  (No schedules configured yet.)")
    else:
        for i, item in enumerate(schedules, start=1):
            print(format_schedule_summary(i, item))
            print("-" * 72)


def build_schedule_interactive(existing=None):
    """Interactive wizard to create or edit a schedule item."""
    is_edit = existing is not None
    item = dict(existing) if is_edit else {}

    print("\n--- " + ("Edit Schedule" if is_edit else "Add New Schedule") + " ---")

    # 1. Name
    item["name"] = prompt_text("1. Schedule Name", default=item.get("name", "New Schedule"))

    # 2. Trigger Type (Recurring Days vs Specific Date)
    print("\n2. Schedule Trigger Type:")
    print("   [1] Repeating Days of Week (e.g., Mon-Fri, Every Day, Sat-Sun)")
    print("   [2] Specific Date (e.g., 2026-10-25)")
    default_trig = "2" if item.get("date") else "1"
    trig_choice = prompt_text("Select trigger type (1 or 2)", default=default_trig)

    if trig_choice == "2":
        item["date"] = prompt_date(default=item.get("date", datetime.now().strftime("%Y-%m-%d")))
        item["days"] = []
    else:
        item.pop("date", None)
        item["days"] = prompt_days(default_list=item.get("days", ["*"]))

    # 3. Time (HH:MM)
    print()
    item["time"] = prompt_time(default=item.get("time", "08:00"))

    # 4. Action Type
    print("\n4. Select Action:")
    print("   [1] Speak Announcement ('say')")
    print("   [2] Unlock for Everyone / Guest Mode ('unlock_for_everyone')")
    print("   [3] Open Door for Duration then Close ('open_for_duration')")

    action_map = {"1": "say", "2": "unlock_for_everyone", "3": "open_for_duration"}
    rev_map = {"say": "1", "unlock_for_everyone": "2", "open_for_duration": "3"}
    default_act = rev_map.get(item.get("action", "say"), "1")

    while True:
        act_choice = prompt_text("Choose action (1, 2, or 3)", default=default_act)
        if act_choice in action_map:
            action = action_map[act_choice]
            item["action"] = action
            break
        print("  -> Please enter 1, 2, or 3.")

    # 5. Action-Specific Parameters
    print()
    if action == "say":
        item["text"] = prompt_text(
            "Vietnamese text to speak",
            default=item.get("text", "Chào buổi sáng, chúc một ngày tốt lành")
        )
        item.pop("duration", None)
        item.pop("actuator_duration", None)
        item.pop("open_delay", None)

    elif action == "unlock_for_everyone":
        print("  [Guest Mode Info] Anyone with a face detected by the camera can enter")
        print("  and will be greeted without a name during this active window.")
        item["duration"] = prompt_float(
            "How long should Guest Mode stay active? (seconds, e.g. 3600 = 1 hour)",
            default=item.get("duration", 3600),
            min_val=10
        )
        item["actuator_duration"] = prompt_float(
            "Actuator open/close travel duration (seconds)",
            default=item.get("actuator_duration", 30),
            min_val=1
        )
        item["open_delay"] = prompt_float(
            "Wait time before closing after each guest enters (seconds)",
            default=item.get("open_delay", 5),
            min_val=1
        )
        item["text"] = prompt_text(
            "Announcement when Guest Mode starts (leave blank for silent start)",
            default=item.get("text", "Chế độ đón khách đã bật, cửa mở tự động cho mọi người"),
            allow_empty=True
        )

    elif action == "open_for_duration":
        print("  [Timed Open Info] Immediately opens the door at the scheduled time,")
        print("  holds it open for the specified duration, and then closes it.")
        item["duration"] = prompt_float(
            "How long to hold the door open before closing? (seconds)",
            default=item.get("duration", 60),
            min_val=1
        )
        item["actuator_duration"] = prompt_float(
            "Actuator open/close travel duration (seconds)",
            default=item.get("actuator_duration", 30),
            min_val=1
        )
        item["text"] = prompt_text(
            "Announcement when opening starts (leave blank for default)",
            default=item.get("text", "Đang mở cửa theo lịch trình"),
            allow_empty=True
        )
        item.pop("open_delay", None)

    return item


def add_schedule(schedules):
    new_item = build_schedule_interactive()
    schedules.append(new_item)
    save_schedules(schedules)


def edit_schedule(schedules):
    if not schedules:
        print("\n[INFO] No schedules available to edit.")
        return
    list_schedules(schedules)
    raw = input("\nEnter schedule number to edit (or press Enter to cancel): ").strip()
    if not raw:
        return
    try:
        idx = int(raw) - 1
        if 0 <= idx < len(schedules):
            updated = build_schedule_interactive(schedules[idx])
            schedules[idx] = updated
            save_schedules(schedules)
        else:
            print("  -> Invalid schedule number.")
    except ValueError:
        print("  -> Please enter a valid number.")


def delete_schedule(schedules):
    if not schedules:
        print("\n[INFO] No schedules available to delete.")
        return
    list_schedules(schedules)
    raw = input("\nEnter schedule number to delete (or 'all' to clear all, Enter to cancel): ").strip().lower()
    if not raw:
        return
    if raw == "all":
        confirm = input("Are you sure you want to delete ALL schedules? (y/N): ").strip().lower()
        if confirm == "y":
            schedules.clear()
            save_schedules(schedules)
        return
    try:
        idx = int(raw) - 1
        if 0 <= idx < len(schedules):
            removed = schedules.pop(idx)
            print(f"[DELETED] Removed '{removed.get('name', 'Schedule')}'")
            save_schedules(schedules)
        else:
            print("  -> Invalid schedule number.")
    except ValueError:
        print("  -> Please enter a valid number.")


def main():
    schedules = load_schedules()

    # Optional quick CLI flags: `python3 manage_schedules.py list`
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd in ("list", "ls", "-l", "--list"):
            list_schedules(schedules)
            return
        elif cmd in ("add", "-a", "--add"):
            add_schedule(schedules)
            return
        elif cmd in ("edit", "-e", "--edit"):
            edit_schedule(schedules)
            return
        elif cmd in ("delete", "del", "rm", "-d", "--delete"):
            delete_schedule(schedules)
            return

    # Interactive Menu Loop
    while True:
        schedules = load_schedules()
        print("\n==========================================")
        print("   DOOR SCHEDULE CONFIGURATOR (CLI)       ")
        print("==========================================")
        print(f" File: {SCHEDULES_FILE}")
        print(f" Loaded Entries: {len(schedules)}")
        print("------------------------------------------")
        print("  1. List all schedules")
        print("  2. Add a new schedule")
        print("  3. Edit an existing schedule")
        print("  4. Delete a schedule")
        print("  5. Exit")
        print("------------------------------------------")

        choice = input("Select an option (1-5): ").strip()

        if choice == "1":
            list_schedules(schedules)
        elif choice == "2":
            add_schedule(schedules)
        elif choice == "3":
            edit_schedule(schedules)
        elif choice == "4":
            delete_schedule(schedules)
        elif choice in ("5", "q", "quit", "exit"):
            print("Exiting schedule configurator.")
            break
        else:
            print("Invalid choice. Please enter 1-5.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
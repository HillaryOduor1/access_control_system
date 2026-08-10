from core.icon_manager import IconManager

if __name__ == "__main__":
    print("Downloading all icons to assets/icons/ ...")
    IconManager().preload_all_to_bundle()
    print("Done! Check the assets/icons/ folder.")
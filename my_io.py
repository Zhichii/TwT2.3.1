# deprecated. use readline instead (wait for me to test on Windows)

import sys
import getch
import unicodedata

def get_char_width(s: str) -> int:
    # By DeepSeek
    if len(s) != 1:
        raise ValueError("输入字符串长度必须为1")
    width_type = unicodedata.east_asian_width(s)
    return int(width_type in ('F', 'W'))+1
def is_visible_char(c : str) -> bool:
    # By DeepSeek
    if len(c) != 1:
        raise ValueError("字符串长度必须为1")
    import unicodedata
    category = unicodedata.category(c)
    excluded_categories = {'Cc', 'Cf', 'Cs', 'Co', 'Cn', 'Zl', 'Zp'}
    if category in excluded_categories:
        return False
    if ord(c) == 0x200B:
        return False
    if 0x200C <= ord(c) <= 0x200F:
        return False
    if 0x202A <= ord(c) <= 0x202E:
        return False
    if 0x2060 <= ord(c) <= 0x206F:
        return False
    if ord(c) == 0xFEFF:
        return False
    return True
def length(string) -> int:
    l = 0
    for i in string:
        l += get_char_width(i)
    return l
def linux_input(prompt : str):
    print(prompt, end="", flush=True)
    cache = []
    ptr = 0 # 代表光标在第ptr个字符前面。ptr从0开始。
    while True:
        k = getch.getkey()
        if isinstance(k, tuple):
            if k[0] == 'LEFT':
                ptr-=1
                if ptr < 0: ptr = 0
                else:
                    sys.stdout.write(f'\033[{get_char_width(cache[ptr])}D')
                    sys.stdout.flush()
            if k[0] == 'RIGHT':
                ptr+=1
                if ptr > len(cache): ptr = len(cache)
                else:
                    sys.stdout.write(f'\033[{get_char_width(cache[ptr-1])}C')
                    sys.stdout.flush()
            if k[0] == 'UNKNOWN':
                if k[1] == b'\x1b[3':
                    if getch.getkey() == '~':
                        if ptr < len(cache):
                            if length(cache[:ptr]) != 0: sys.stdout.write(f'\033[{length(cache[:ptr])}D')
                            sys.stdout.flush()
                            print(length(cache)*" ", end=length(cache)*"\b", flush=True)
                            cache.pop(ptr)
                            print("".join(cache), end=length(cache)*"\b", flush=True)
                            if length(cache[:ptr]) != 0: sys.stdout.write(f'\033[{length(cache[:ptr])}C')
                            sys.stdout.flush()
            continue
        if length(cache[:ptr]) != 0: sys.stdout.write(f'\033[{length(cache[:ptr])}D')
        sys.stdout.flush()
        print(length(cache)*" ", end=length(cache)*"\b", flush=True)
        if is_visible_char(k):
            cache.insert(ptr, k)
            ptr += 1
        if k in ["\x03"]:
            raise KeyboardInterrupt
        if k in ["\r","\n"]:
            break
        if k == "\x7f":
            ptr -= 1
            if ptr < 0:
                ptr = 0
            elif ptr >= 0:
                cache.pop(ptr)
        print("".join(cache), end=length(cache)*"\b", flush=True)
        if length(cache[:ptr]) != 0: sys.stdout.write(f'\033[{length(cache[:ptr])}C')
        sys.stdout.flush()
    print("".join(cache))
    return ("".join(cache))

if __name__ == "__main__":
    try:
        user_input = linux_input("请输入: ")
        print(f"你输入了: {user_input}")
    except KeyboardInterrupt:
        print("\n输入被中断")
"""
[chatEvent]
__addr__ : address
message : value
^start.*middle.*end$ : value
"""
from itertools import combinations
from operator import itemgetter
from random import randint

from eudplib import *
import sys

Addr, lenAddr, ptrAddr, patternAddr = None, None, None, None
minlen, maxlen = 78, 0
KEY1, KEY2 = randint(0, 0xFFFFFFFF), randint(0, 0xFFFFFFFF)


class Hash:
    R1, R2, R3, R4, R5, R6 = 7, 8, 16, 9, 11, 16
    KC1 = 0x736F6D65
    KC2 = 0x646F7261
    KC3 = 0x6C796765
    KC4 = 0x74656462

    @staticmethod
    def rot(a, b):
        a, b = a & 0xFFFFFFFF, b & 0xFFFFFFFF
        return ((a << b) | (a >> (32 - b))) & 0xFFFFFFFF

    def round(self):
        self.v0 += self.v1
        self.v2 += self.v3
        self.v1 = Hash.rot(self.v1, Hash.R1)
        self.v3 = Hash.rot(self.v3, Hash.R2)
        self.v1 ^= self.v0
        self.v3 ^= self.v2
        self.v0 = Hash.rot(self.v0, Hash.R3)
        self.v2 += self.v1
        self.v0 += self.v3
        self.v1 = Hash.rot(self.v1, Hash.R4)
        self.v3 = Hash.rot(self.v3, Hash.R5)
        self.v1 ^= self.v2
        self.v3 ^= self.v0
        self.v2 = Hash.rot(self.v2, Hash.R6)
        self.v0 &= 0xFFFFFFFF
        self.v1 &= 0xFFFFFFFF
        self.v3 &= 0xFFFFFFFF

    def ksetup(self, k0, k1):
        self.v0 = k0 ^ Hash.KC1
        self.v1 = k1 ^ Hash.KC2
        self.v2 = k0 ^ Hash.KC3
        self.v3 = k1 ^ Hash.KC4

    def getword(self, s):
        toffset = self.offset
        shift, out = 0, 0
        while True:
            if toffset >= len(s):
                out |= (len(s) & 0xFF) << 24
                self.offset = len(s) + 1
                return out
            out |= s[toffset] << shift
            shift += 8
            toffset += 1
            if toffset >= self.offset + 4:
                self.offset = toffset
                break
        return out

    def hash(self, s, k1, k2):
        self.offset = 0
        self.ksetup(k1, k2)
        while self.offset <= len(s):
            m = self.getword(s)
            self.v3 ^= m
            for _ in range(2):
                self.round()
            self.v0 ^= m
        self.v2 ^= 0xFF
        for _ in range(4):
            self.round()
        return self.v0 ^ self.v1 ^ self.v2 ^ self.v3

    def test(self):
        s = b""
        for i in range(10):
            o = self.hash(s, 0x03020100, 0x07060504)
            print(f"{o:08x}")
            s += bytes([i])


class EUDHash(Hash):
    rotator = EUDVariable()

    def __init__(self):
        self.v0 = EUDVariable()
        self.v1 = EUDVariable()
        self.v2 = EUDVariable()
        self.v3 = EUDVariable()
        self.offset = EUDVariable()
        # self.epd, self.subp = EUDCreateVariables(2)

    @staticmethod
    def rot(a, b):
        # in-place rotate-left
        EUDHash.rotator << 0
        for i in range(32 - b):
            RawTrigger(
                conditions=a.AtLeastX(1, 1 << i),
                actions=EUDHash.rotator.AddNumber(1 << (i + b)),
            )
        for i in range(b):
            RawTrigger(
                conditions=a.AtLeastX(1, 1 << (32 - b + i)),
                actions=EUDHash.rotator.AddNumber(1 << i),
            )
        VProc(EUDHash.rotator, EUDHash.rotator.SetDest(a))

    def round(self):
        f = getattr(self, "roundf", None)
        if f is None:

            @EUDFunc
            def f():
                SetVariables([self.v0, self.v2], [self.v1, self.v3], [Add, Add])
                EUDHash.rot(self.v1, Hash.R1)
                EUDHash.rot(self.v3, Hash.R2)
                self.v1 ^= self.v0
                self.v3 ^= self.v2
                EUDHash.rot(self.v0, Hash.R3)
                SetVariables([self.v2, self.v0], [self.v1, self.v3], [Add, Add])
                EUDHash.rot(self.v1, Hash.R4)
                EUDHash.rot(self.v3, Hash.R5)
                self.v1 ^= self.v2
                self.v3 ^= self.v0
                EUDHash.rot(self.v2, Hash.R6)

            self.roundf = f
        f()

    def ksetup(self, k0, k1):
        SetVariables(
            [self.v0, self.v1, self.v2, self.v3],
            [k0 ^ Hash.KC1, k1 ^ Hash.KC2, k0 ^ Hash.KC3, k1 ^ Hash.KC4],
        )

    def getword(self, ptr, length):  # TODO: use EPD!!!
        toffset, prevptr, shift, out = EUDCreateVariables(4)
        br = EUDByteReader()
        if EUDIfNot()(prevptr == ptr):
            br.seekoffset(ptr)
        EUDEndIf()
        SeqCompute(
            [
                (out, SetTo, 0),
                (prevptr, SetTo, 4),
                (prevptr, Add, ptr),
                (toffset, SetTo, self.offset),
            ]
        )
        if EUDWhile()(True):
            if EUDIf()(toffset >= length):
                out |= f_bitlshift(length & 0xFF, 24)
                self.offset << length + 1
                EUDBreak()
            EUDEndIf()
            out |= f_bitlshift(br.readbyte(), shift)
            shift += 8
            toffset += 1
            if EUDIf()(toffset >= self.offset + 4):
                self.offset << toffset
                EUDBreak()
            EUDEndIf()
        EUDEndWhile()
        return out

    def hash(self, ptr, length, k1, k2):
        self.offset << 0
        self.ksetup(k1, k2)
        if EUDWhile()(self.offset <= length):
            m = self.getword(ptr, length)  # FIXME
            self.v3 ^= m
            for _ in range(2):
                self.round()
            self.v0 ^= m
        EUDEndWhile()
        self.v2 ^= 0xFF
        for _ in range(4):
            self.round()
        return self.v0 ^ self.v1 ^ self.v2 ^ self.v3

    def test(self):
        s = b""
        for i in range(10):
            d = Db(s + b"\0")
            o = self.hash(d, len(s), 0x03020100, 0x07060504)
            f_printAll("{:x}", o)
            s += bytes([i])


def onInit():
    global Addr, lenAddr, ptrAddr, patternAddr, minlen, maxlen, chatDict, regexDict, rList
    chatDict, regexDict, rList = {}, {}, []
    sys.stdout.reconfigure(encoding="utf-8")
    h = Hash()

    def delrem4(x):
        return x - x % 4

    for k, v in settings.items():
        if k.upper() == "__ENCODING__":
            continue
        try:
            v = int(v, 0)
        except ValueError:
            raise EPError(f"right-sided value is not a number! {k} : {v}")
        if k.upper() == "__ADDR__":
            ep_assert(Addr is None, f"multiple addr error. {k} : {v}")
            Addr = delrem4(v)  # 주소를 정수로 가져온다.
        elif k.upper() == "__LENADDR__":
            ep_assert(lenAddr is None, f"multiple lenAddr error. {k} : {v}")
            lenAddr = delrem4(v)
        elif k.upper() == "__PTRADDR__":
            ep_assert(ptrAddr is None, f"multiple ptrAddr error. {k} : {v}")
            ptrAddr = delrem4(v)
        elif k.upper() == "__PATTERNADDR__":
            ep_assert(patternAddr is None, f"multiple patternAddr error. {k} : {v}")
            patternAddr = delrem4(v)
        elif k[:1] == "^" and k[-1:] == "$" and k.count(".*") == 2:
            ep_assert(v > 0, f"Value should be greater than 0. {k} : {v}")
            t = k[1:-1].encode("utf-8")
            ep_assert(
                len(t) <= 82, f'chat pattern "{k}" is too long to type (up to 78 bytes)'
            )
            start, middle, end = t.split(b".*")
            key = (start, middle, end)
            ep_assert(key not in regexDict, f"Duplicated regex pattern. {k} : {v}")
            regexDict[key] = v
            rList.append(
                EUDArray(
                    [
                        Db(start + b"\0"),
                        Db(middle + b"\0"),
                        Db(end + b"\0"),
                        v,
                        len(start),
                        len(end),
                    ]
                )
            )
        else:
            ep_assert(v > 1, f"Value should be greater than 1. {k} : {v}")
            t = k.encode("utf-8")
            ep_assert(
                len(t) <= 78, f'chat message "{k}" is too long to type (up to 78 bytes)'
            )
            if len(t) > maxlen:
                maxlen = len(t)
            if len(t) < minlen:
                minlen = len(t)
            c = h.hash(t, KEY1, KEY2)
            ep_assert(c not in chatDict, f"Duplicated chat hash. {k} : {v}")
            chatDict[c] = (k, v)

    global rListlen
    rListlen = len(rList)
    rList = EUDArray(rList)

    detect_duplicates = list()
    for v in (Addr, lenAddr, ptrAddr, patternAddr):
        if v and v >= 1:
            detect_duplicates.append(v)
    if not all(a != b for a, b in combinations(detect_duplicates, 2)):
        raise EPError(f"Duplicated address ; {detect_duplicates}")

    if Addr is None:
        Addr = 0x58D900  # default address
    print(f"__addr__ : 0x{Addr:X}")
    if lenAddr:
        print(f"__lenAddr__ : 0x{lenAddr:X}")
    if ptrAddr:
        print(f"__ptrAddr__ : 0x{ptrAddr:X}")
    if patternAddr:
        print(f"__patternAddr__ : 0x{patternAddr:X}")
    for r, v in regexDict.items():
        print("^{0}.*{1}.*{2}$ : {3}".format(*r, v))
    if regexDict and not patternAddr:
        raise EPError(
            "patternAddr not defined for regex patterns (^start.*middle.*end$)."
        )
    elif regexDict and patternAddr:
        print(
            f"Memory(0x{patternAddr:X}, Exactly, right-sided value); <- Use this condition for patterned chat-detect (desync)"
        )
    for k, v in chatDict.values():
        print('{} : "{}"'.format(k, v))
    print("(not belong to any pattern) : 1")
    print(
        f"Memory(0x{Addr:X}, Exactly, right-sided value); <- Use this condition for chat-detect (desync)"
    )
    print(f"Total: {len(chatDict)}")


onInit()

con = [[Forward() for _ in range(2)] for __ in range(5)]
act = [[Forward() for _ in range(2)] for __ in range(5)]
chatptr, exit = EUDVariable(), Forward()
cp = [[Forward() for _ in range(2)] for __ in range(3)]
trg = [Forward() for _ in range(2)]
event_init, chat_detected = Forward(), Forward()
detect_oddline, detect_evenline = Forward(), Forward()


@EUDFunc
def f_init():
    pNumber = f_getuserplayerid()  # 플레이어 번호 (비공유)
    idptr = 0x57EEEB + 36 * pNumber
    idlen = f_strlen(idptr)
    idDb, myChat = Db(28), Db(b":\x07 ")
    DoActions([SetMemory(idDb + i, SetTo, 0) for i in range(0, 28, 4)])
    f_memcpy(idDb, idptr, idlen)
    f_dbstr_addstr(idDb + idlen, myChat)

    odd, even = EUDCreateVariables(2)
    set_mask = [Forward() for _ in range(4)]

    DoActions(
        [
            SetMemory(event_init + 348, SetTo, 0x640B63 + idlen),
            odd.SetNumber(0),
            even.SetNumber(16),
            SetMemory(set_mask[0] + 16, SetTo, EPD(detect_oddline + 8)),
            SetMemory(set_mask[1] + 16, SetTo, EPD(detect_oddline + 8 + 8)),
            SetMemory(set_mask[2] + 16, SetTo, EPD(detect_evenline + 8)),
            SetMemory(set_mask[3] + 16, SetTo, EPD(detect_evenline + 8 + 8)),
        ]
        + [
            [
                SetMemory(detect_oddline + 8 + 20 * c, SetTo, 0),  # 비트 마스크
                SetMemory(detect_oddline + 8 + 8 + 20 * c, SetTo, 0),  # 값
            ]
            for c in range(7)
        ]
        + [
            [
                SetMemory(detect_evenline + 8 + 20 * c, SetTo, 0),  # 비트 마스크
                SetMemory(detect_evenline + 8 + 8 + 20 * c, SetTo, 0),  # 값
            ]
            for c in range(8)
        ]
    )
    br = EUDByteReader()
    br.seekepd(EPD(idDb))
    if EUDWhile()(True):
        b = br.readbyte()
        EUDBreakIf(b == 0)
        DoActions(
            [
                set_mask[0] << SetMemory(0, Add, f_bitlshift(0xFF, odd)),
                set_mask[1] << SetMemory(0, Add, f_bitlshift(b, odd)),
                set_mask[2] << SetMemory(0, Add, f_bitlshift(0xFF, even)),
                set_mask[3] << SetMemory(0, Add, f_bitlshift(b, even)),
                odd.AddNumber(8),
                even.AddNumber(8),
            ]
        )
        RawTrigger(
            conditions=odd.AtLeast(32),
            actions=[
                odd.SubtractNumber(32),
                SetMemory(set_mask[0] + 16, Add, 5),
                SetMemory(set_mask[1] + 16, Add, 5),
            ],
        )
        RawTrigger(
            conditions=even.AtLeast(32),
            actions=[
                even.SubtractNumber(32),
                SetMemory(set_mask[2] + 16, Add, 5),
                SetMemory(set_mask[3] + 16, Add, 5),
            ],
        )
    EUDEndWhile()


def onPluginStart():
    f_init()


@EUDFunc
def f_chatcmp():
    chatlen = f_strlen(chatptr)
    assign_list = []
    if lenAddr:
        assign_list.append((EPD(lenAddr), SetTo, chatlen))
    if ptrAddr:
        assign_list.append((EPD(ptrAddr), SetTo, chatptr))
    if assign_list:
        SeqCompute(assign_list)
    if EUDIf()([chatlen >= minlen, chatlen <= maxlen]):
        PushTriggerScope()
        exitter = RawTrigger(nextptr=exit, actions=SetDeaths(0, SetTo, 0, 0))
        PopTriggerScope()
        e = EUDHash()
        o = e.hash(chatptr, chatlen, KEY1, KEY2)
        for c, kv in chatDict.items():
            trig, nptr = Forward(), Forward()
            trig << RawTrigger(
                conditions=o.Exactly(c),
                actions=[
                    SetMemory(Addr, SetTo, kv[1]),
                    SetNextPtr(trig, exitter),
                    SetMemory(exitter + 344, SetTo, EPD(trig) + 1),
                    SetMemory(exitter + 348, SetTo, nptr),
                ],
            )
            nptr << NextTrigger()
    EUDEndIf()
    if rListlen >= 1:
        for i in EUDLoopRange(rListlen):
            subArray = EUDArray.cast(rList[i])
            if EUDIf()(f_memcmp(chatptr, subArray[0], subArray[4]) == 0):
                endlen = subArray[5]
                if EUDIf()(
                    f_memcmp(chatptr + chatlen - endlen, subArray[2], endlen) == 0
                ):
                    if EUDIfNot()(f_strnstr(chatptr, subArray[1], chatlen) == -1):
                        f_dwwrite(patternAddr, subArray[3])
                        EUDJump(exit)
                    EUDEndIf()
                EUDEndIf()
            EUDEndIf()


temp = EUDVariable()


def chatEvent():
    event_init << RawTrigger(  # 조건의 EPD 초기화
        actions=[chatptr.SetNumber(0x640B63)]
        + [
            SetMemory(detect_oddline + 8 + 4 + 20 * c, SetTo, EPD(0x640B60) + c)
            for c in range(7)
        ]
        + [
            SetMemory(detect_evenline + 8 + 4 + 20 * c, SetTo, EPD(0x640C3A) + c)
            for c in range(8)
        ]
    )

    if EUDWhile()(chatptr <= 0x640B60 + 436 * 6 - 1):
        oddline_nptr, evenline_nptr = Forward(), Forward()
        # odd linenumber
        detect_oddline << RawTrigger(
            conditions=[DeathsX(0, Exactly, 0, 0, 0) for _ in range(7)],
            actions=[
                SetMemory(chat_detected + 8 + 320 + 16, SetTo, EPD(detect_oddline + 4)),
                SetMemory(chat_detected + 8 + 320 + 20, SetTo, oddline_nptr),
                SetNextPtr(detect_oddline, chat_detected),
            ],
        )
        oddline_nptr << NextTrigger()

        EUDBreakIf(chatptr >= 0x640B60 + 436 * 5)
        # even linenumber
        detect_evenline << RawTrigger(
            conditions=[DeathsX(0, Exactly, 0, 0, 0) for _ in range(8)],
            actions=[
                chatptr.AddNumber(218),
                SetMemory(chat_detected + 344, SetTo, EPD(detect_evenline + 4)),
                SetMemory(chat_detected + 348, SetTo, evenline_nptr),
                SetNextPtr(detect_evenline, chat_detected),
            ],
        )
        evenline_nptr << NextTrigger()

        EUDSetContinuePoint()
        DoActions(
            [chatptr.AddNumber(436)]
            + [SetMemory(detect_oddline + 12 + 20 * c, Add, 109) for c in range(7)]
            + [SetMemory(detect_evenline + 12 + 20 * c, Add, 109) for c in range(8)]
        )
    EUDEndWhile()
    chatptr << 0


def beforeTriggerExec():
    if EUDIf()(Memory(Addr, Exactly, -1)):
        f_init()
    EUDEndIf()

    DoActions(
        [SetMemory(Addr, SetTo, 0), chatptr.SetNumber(0)]  # 초기화
        + [SetMemory(lenAddr, SetTo, 0) if lenAddr else []]
        + [SetMemory(ptrAddr, SetTo, 0) if ptrAddr else []]
        + [SetMemory(patternAddr, SetTo, 0) if rListlen else []]
    )

    oldcp = f_getcurpl()
    chatEvent()

    PushTriggerScope()
    chat_detected << RawTrigger(
        actions=[SetMemory(0, SetTo, 0), SetMemory(Addr, SetTo, 1)]
    )
    f_wwrite(chatptr - 2, 0x0720)
    f_chatcmp()
    SetNextTrigger(exit)
    PopTriggerScope()

    exit << NextTrigger()
    f_setcurpl(oldcp)

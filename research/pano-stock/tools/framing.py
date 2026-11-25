# SPDX-License-Identifier: GPL-3.0-or-later
def header(flags,seq,ack=0):
    if flags not in (0x80,0x40) or not 0<=seq<4096 or not 0<=ack<4096:
        raise ValueError("diagnostic transport flags or sequence invalid")
    return bytes([1,flags])+((seq<<12)|ack).to_bytes(3,"big")+bytes(3)

def decode(data):
    if len(data)<8 or data[0]!=1:raise ValueError("invalid TNP")
    seqack=int.from_bytes(data[2:5],"big")
    return data[1],seqack>>12,seqack&4095,data[8:]

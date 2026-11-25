import sys
from hashlib import sha256
sys.path.insert(0,"../manifest-core")
from fixtures import encode,emit
raw=bytes((i*13+7)%256 for i in range(513))
m={"manifest_version":1,"image_id":"integration-fixture","image_version":"1","image_role":"application","supported_targets":[{"board_id":"pano-g2","board_revision":"b","fpga_part":"xc6slx150-2-fgg484","bsp_profile":"pano-g2-revb/1"}],"image_length":len(raw),"image_sha256":sha256(raw).digest(),"required_rescue_api":[1,0],"config_format":"xilinx-spartan6-spi","required_features":[],"build_provenance":{"git_commit":"0123456789abcdef"*2+"01234567","dependency_pins":["fixture@1"],"toolchain":"fixture"}}
emit("raw",raw)
emit("manifest",encode(m))
emit("digest",sha256(encode(m)).digest())
old_raw=bytes((i*7+3)%256 for i in range(513))
old=dict(m,image_id="old-fixture",image_sha256=sha256(old_raw).digest())
emit("old_raw",old_raw)
emit("old_manifest",encode(old))
emit("old_digest",sha256(encode(old)).digest())

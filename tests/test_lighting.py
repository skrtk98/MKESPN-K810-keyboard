import json
from pathlib import Path
import unittest
from mkespn_k810_keyboard.lighting import MODES, decode_lighting, set_lighting, lighting_blocks


class LightingTests(unittest.TestCase):
    def test_fields_match_original_x86_apply(self):
        vectors=json.loads((Path(__file__).parent/'vendor_lighting_vectors.json').read_text())
        for case in vectors['cases']:
            data=bytearray(248)
            for block in case['blocks']:
                at=block['write_address']-0xe0
                data[at:at+8]=bytes.fromhex(block['data'])
            decoded=decode_lighting(data)
            self.assertEqual({k:decoded[k] for k in case['fields']},case['fields'])
            fields=dict(case['fields']); fields['mode']=MODES[fields.pop('mode_code')]
            after=set_lighting(bytes([0xaa])*248,fields)
            self.assertEqual({k:decode_lighting(after)[k] for k in case['fields']},case['fields'])
            # Palette shares bytes with mode-enable flags: preserve high nibbles.
            self.assertTrue(all(after[i]&0xf0==0xa0 for i in range(2,15,2)))
            self.assertEqual(after[0],0xaa)
            self.assertEqual(after[0x1b:],bytes([0xaa])*(248-0x1b))
            self.assertEqual(after[15]&0xfc,0xa8)

    def test_light_write_boundaries_and_validation(self):
        before=bytes([0xaa])*248
        after=set_lighting(before,{'mode':'off'})
        self.assertEqual([o for o,b in lighting_blocks(before,after)],[0,24])
        with self.assertRaises(ValueError):set_lighting(before,{'speed':7})
        with self.assertRaises(ValueError):set_lighting(before,{'mode':'unknown'})
        with self.assertRaises(ValueError):set_lighting(before,{'colors_enabled':0})
        bad=bytearray(after);bad[72]=0
        with self.assertRaises(ValueError):lighting_blocks(before,bad)


if __name__=='__main__':unittest.main()

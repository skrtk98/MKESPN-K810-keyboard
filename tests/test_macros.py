import json
from pathlib import Path
import unittest

from mkespn_k810_keyboard.actions import ACTIONS
from mkespn_k810_keyboard.macros import compile_macro, macro_entry, plan_macro, restore_macro_blocks
from mkespn_k810_keyboard.protocol import keycode

VECTORS=json.loads(Path(__file__).with_name('vendor_extended_vectors.json').read_text())


def spec_from_fixture(spec):
    events=[]
    for original in spec['events']:
        event=original.copy()
        if event['type'].startswith('key-'):
            event['key']=hex(event.pop('code'))
        elif event['type'].startswith('mouse-'):
            event['button']={241:'left',243:'right',242:'middle'}[event.pop('code')]
        events.append(event)
    return dict(spec,events=events)


def empty_image():
    data=bytearray([255]*8192)
    data[0xd0:0xd8]=bytes.fromhex('e11ee000f00f0000')
    data[0xe0:0xe8]=bytes.fromhex('c0f01f0f1fff00f0')
    data[0xfe:0x100]=bytes.fromhex('d801')
    data[0x1d8:0x240]=bytes(104)
    return bytes(data)


class MacroTests(unittest.TestCase):
    def test_repeat_modes_follow_original_skin_handlers(self):
        from mkespn_k810_keyboard.macros import MODES
        by_button={e['button']:e['mode'] for e in VECTORS['repeat_buttons']}
        self.assertEqual(MODES['while-held'],by_button[10])
        self.assertEqual(MODES['until-click'],by_button[11])
        self.assertEqual(MODES['repeat'],by_button[12])

    def test_mouse_codes_match_original_insertion_handlers(self):
        from mkespn_k810_keyboard.macros import BUTTONS
        vectors=json.loads(Path(__file__).with_name('vendor_mouse_handler_vectors.json').read_text())
        for entry in vectors['cases']:
            self.assertEqual(BUTTONS[entry['button']],entry['code'])
            self.assertEqual(entry['event_type'],1 if entry['down'] else 2)

    def test_led_pattern_sequences_match_original_serializer_and_are_protected(self):
        from mkespn_k810_keyboard.lighting import MODES
        vectors=json.loads(Path(__file__).with_name('vendor_macro_extension_vectors.json').read_text())
        for entry in vectors['cases']:
            if entry['code']!=0xf9:continue
            raw=bytes.fromhex(entry['led_hex'])
            sequence=[dict(mode=MODES[raw[i]],color=raw[i+1],duration_ms=raw[i+2]*100) for i in range(4,len(raw),4)]
            spec={'events':[{'type':'led','behavior':entry['types'][0]-13,'sequence':sequence}]}
            payload,count,mode=compile_macro(spec,0x240)
            expected=''.join(w['data'] for w in entry['writes'] if w['write_address']>=0x240)
            self.assertEqual(payload.hex(),expected)
            first,_,_=plan_macro(empty_image(),0xe0,'kp1',spec)
            second,_,_=plan_macro(first,0xe0,'kp2',{'events':[{'type':'delay'}]})
            self.assertEqual(second[0x240:0x240+len(payload)],first[0x240:0x240+len(payload)])

    def test_actions_match_original_mapper(self):
        original={x['code'] for x in VECTORS['actions'] if x['unique_index']!=18}
        self.assertEqual(set(ACTIONS.values()),original)
        for name,code in ACTIONS.items(): self.assertEqual(keycode(name),code)

    def test_payload_and_descriptor_match_original_serializer(self):
        for entry in VECTORS['macros']:
            payload,count,mode=compile_macro(spec_from_fixture(entry['spec']))
            self.assertEqual(payload.hex(),entry['payload'])
            self.assertEqual(macro_entry(0x240,count,mode).hex(),entry['descriptor'])

    def test_allocation_preserves_existing_macros_and_unrelated_bytes(self):
        before=empty_image()
        spec={'events':[{'type':'mouse-down','button':'left'},{'type':'mouse-up','button':'left'}]}
        first,blocks,slot=plan_macro(before,0xe0,'kp1',spec)
        self.assertEqual(slot,0)
        second,other,slot=plan_macro(first,0xe0,'kp2',spec)
        self.assertEqual(slot,1)
        self.assertEqual(second[0x240:0x248],first[0x240:0x248])
        self.assertEqual(second[0x1d8:0x1dd],first[0x1d8:0x1dd])
        allowed={i for address,data in other for i in range(address,address+len(data))}
        self.assertTrue(all(a==b or i in allowed for i,(a,b) in enumerate(zip(first,second))))
        restored,_=restore_macro_blocks(second,before,0xe0)
        self.assertEqual(restored,before)

    def test_refuse_unbalanced_events_bad_addresses_and_full_memory(self):
        with self.assertRaises(ValueError): compile_macro({'events':[{'type':'key-down','key':'a'}]})
        with self.assertRaises(ValueError): compile_macro({'events':[{'type':'move','x':999999,'y':0}]})
        data=bytearray(empty_image());data[0x240:]=bytes(8192-0x240)
        with self.assertRaises(ValueError): plan_macro(bytes(data),0xe0,'kp1',{'events':[{'type':'scroll','steps':1}]})


if __name__=='__main__': unittest.main()

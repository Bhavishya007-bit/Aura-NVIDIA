"""Create a small self-authored, annotated course fixture; no external images."""
from pathlib import Path
import argparse
import pymupdf


def make(path):
    doc = pymupdf.open()
    pages = [
        ('Filament treadmilling', 'Treadmilling is a behavior of actin filaments in which addition of subunits at the plus end balances loss at the minus end. Equal addition and loss maintain near-constant length. Greater addition than loss causes net growth. The diagram shows balanced turnover, not whole-filament translation.'),
        ('Microtubule dynamic instability', 'Dynamic instability is switching between microtubule growth and shrinkage. It differs from treadmilling, which describes balanced turnover at near-constant length. The diagram shows two alternate states, not simultaneous balanced turnover.'),
        ('Speed from distance and time', 'Speed equals distance divided by elapsed time: v = d/t. Distance d is in metres (m), elapsed time t is in seconds (s), and speed v is in metres per second (m/s). Example: d = 12 m and t = 2 s give v = 6 m/s.'),
        ('Force, mass and acceleration', 'Force equals mass multiplied by acceleration: F = m*a. Mass m is in kilograms (kg), acceleration a is in metres per second squared (m/s^2), and force F is in newtons (N). Example: m = 2 kg and a = 3 m/s^2 give F = 6 N.'),
    ]
    for number,(title,text) in enumerate(pages,1):
        page=doc.new_page(width=612,height=792)
        page.insert_text((45,55),title,fontsize=20)
        page.insert_textbox(pymupdf.Rect(45,85,567,230),text,fontsize=13)
        if number == 1:
            for x in range(140,440,40):
                page.draw_circle((x,330),14,color=(.15,.4,.6),fill=(.65,.8,.9))
            page.insert_text((60,300),'MINUS END: loss',fontsize=12)
            page.insert_text((365,300),'PLUS END: addition',fontsize=12)
            page.draw_line((510,330),(465,330),color=(0,.4,0),width=3)
            page.draw_line((465,330),(476,323),color=(0,.4,0),width=3)
            page.draw_line((465,330),(476,337),color=(0,.4,0),width=3)
            page.draw_line((115,330),(65,330),color=(.7,0,0),width=3)
            page.draw_line((65,330),(76,323),color=(.7,0,0),width=3)
            page.draw_line((65,330),(76,337),color=(.7,0,0),width=3)
            page.insert_text((95,390),'Equal addition and loss: length stays approximately constant.',fontsize=12)
        elif number == 2:
            page.insert_text((65,300),'GROWTH',fontsize=15)
            page.draw_line((190,295),(470,295),color=(0,.4,0),width=5)
            page.insert_text((65,370),'SHRINKAGE',fontsize=15)
            page.draw_line((190,365),(305,365),color=(.7,0,0),width=5)
            page.insert_text((65,425),'Alternate states: growth <-> shrinkage',fontsize=13)
        elif number == 3:
            page.draw_line((90,460),(500,460));page.draw_line((90,460),(90,260))
            page.draw_line((90,460),(450,280),color=(.1,.4,.7),width=3)
            page.insert_text((85,480),'0',fontsize=12);page.insert_text((445,480),'2 s',fontsize=12)
            page.insert_text((30,280),'12 m',fontsize=12)
            page.insert_text((240,520),'Elapsed time (s)',fontsize=13)
            page.insert_text((50,245),'Distance (m)',fontsize=13)
        else:
            page.insert_text((110,320),'F = m * a',fontsize=28)
            page.insert_text((110,370),'2 kg * 3 m/s^2 = 6 N',fontsize=20)
        page.insert_text((45,745),f'Aura team-built evaluation fixture | Page {number}',fontsize=10)
    path.parent.mkdir(parents=True,exist_ok=True);doc.save(path);doc.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='evaluation/demo_material.pdf')
    args=parser.parse_args();make(Path(args.output));print(args.output)

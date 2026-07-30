# Embedding benchmark

Sample: 300 active events with category labels. Metric: kNN precision@5 (do an event's nearest neighbours share its label?).

All models via the OpenRouter gateway (identical conditions).

| model | dim | p@5 category | p@5 subcategory | time |
|---|---|---|---|---|
| openai/text-embedding-3-small | 1536 | 0.619 | 0.533 | 10.6s / 300 events |
| qwen/qwen3-embedding-8b | 4096 | 0.561 | 0.505 | 76.2s / 300 events |

## Golden-query retrievals (verify by hand)
Cross-lingual DE<->EN probes — a human judges whether the top-5 are correct.

### openai/text-embedding-3-small (dim=1536)

**q01 [semantic_de] Jazzkonzert heute Abend**
- 0.545 [culture/None] Jazzwoche Berlin
- 0.481 [culture/None] DER TANZENDE SONNTAG
- 0.460 [music/jazz-blues] Hat Bar Live Jam Sessions
- 0.454 [music/jazz-blues] Christian Müller Quartett
- 0.451 [meetups/None] Musikkurs für 2-5- jährige Kinder 15:45 bei ENNA: Heute gibt es Smooth

**q02 [semantic_en] jazz concert tonight**
- 0.506 [music/jazz-blues] Hat Bar Live Jam Sessions
- 0.475 [culture/None] Jazzwoche Berlin
- 0.433 [music/jazz-blues] Irish & Folk Open Session
- 0.409 [culture/None] DER TANZENDE SONNTAG
- 0.389 [culture/None] Musical Concert: Ragas Meet Bollywood

**q03 [cross_lingual] Flohmarkt am Sonntag**
- 0.621 [markets/flea-market] Ikea Flohmarkt Südkreuz
- 0.552 [markets/None] Flowmarkt Schöneberg
- 0.515 [markets/craft-market] Berliner Staudenmarkt
- 0.505 [food/weekly-market] Wochenmarkt Leopoldplatz
- 0.463 [culture/None] DER TANZENDE SONNTAG

**q04 [cross_lingual] vintage flea market**
- 0.470 [markets/flea-market] Ikea Flohmarkt Südkreuz
- 0.397 [markets/None] Flowmarkt Schöneberg
- 0.351 [markets/craft-market] Berliner Staudenmarkt
- 0.313 [food/weekly-market] Wochenmarkt Leopoldplatz
- 0.279 [nightlife/None] Perfumed Sundays

**q05 [semantic_de] Techno Party in Neukölln**
- 0.614 [nightlife/None] Daytime Berlin Underground Party Tour
- 0.605 [nightlife/None] Electric Monday@Kitkat
- 0.549 [nightlife/None] Walk'n' Dance - Silent Disco Walking Tours
- 0.533 [nightlife/None] Ecstatic Dance & Cacao Journey + Tea & Snacks
- 0.516 [nightlife/None] Else x PuMp w Anja Schneider, Hilit Kolet, icykof, Radio Slave, Tal Fu

**q06 [semantic_en] underground electronic music**
- 0.452 [nightlife/None] Dark Monday
- 0.441 [nightlife/None] Else x PuMp w Anja Schneider, Hilit Kolet, icykof, Radio Slave, Tal Fu
- 0.433 [nightlife/None] Electric Monday@Kitkat
- 0.427 [nightlife/None] Hypnogogia
- 0.417 [nightlife/None] manic.monda mit Pablo Cornejo (Chile) !FREE ENTRY

**q07 [vibe_no_keyword] etwas Chilliges nach der Arbeit**
- 0.426 [culture/None] Fit mit Grit
- 0.404 [culture/None] Fit mit Grit
- 0.399 [nightlife/None] Gezapftes Bier 0,5l 3 € - täglich Kippzeit in der BESTE
- 0.399 [nightlife/None] SPRITZ HOUR @ Lost my Voice Bar
- 0.398 [family/kids-program] Mitmach-Nachmittag  mit Tante Milli Tausendgrün

**q08 [family] etwas mit Kindern unternehmen**
- 0.510 [family/kids-program] Mitmach-Nachmittag  mit Tante Milli Tausendgrün
- 0.502 [family/None] Krabbelgruppen im Kindercafé des Stadtteilzentrums Kaulsdorf
- 0.501 [family/kids-program] Krabbelgruppen im Kindercafé des Stadtteilzentrums Kaulsdorf
- 0.495 [meetups/None] Musikkurs für 2-5- jährige Kinder 15:45 bei ENNA: Heute gibt es Smooth
- 0.492 [family/family-event] Leseclub

**q09 [family] fun activities for kids**
- 0.418 [meetups/None] Musikkurs für 2-5- jährige Kinder 15:45 bei ENNA: Heute gibt es Smooth
- 0.393 [family/family-event] Bastel-Montag
- 0.388 [family/family-event] Drinnen oder draußen spielen
- 0.385 [family/kids-program] Krabbelgruppen im Kindercafé des Stadtteilzentrums Kaulsdorf
- 0.384 [family/family-event] Family & Friends Gaming in der Bibliothek

**q10 [semantic_de] Ausstellung zeitgenössische Kunst**
- 0.585 [culture/None] Ausstellungseröffnung EN-TFAL-TET
- 0.582 [culture/exhibition] Ausstellung „Das beste Kennenlernen“ von Jürgen Eisenacher
- 0.579 [culture/exhibition] ZEITFELDER - TIMEFIELDS .................. Amer Akel - Pfelder - Simon
- 0.575 [culture/exhibition] Der Kunstverein Tiergarten e. V. mit der Ausstellung “Critical Friends
- 0.573 [culture/exhibition] Bedrohung / Zagrożenie / Menace ......... Gruppenausstellung

**q11 [facet_combo] free open air cinema**
- 0.402 [culture/None] Die Welt der Traumtiere
- 0.370 [culture/theater] HOHEITSZEICHEN  Moving Image Sculpture #3
- 0.351 [nightlife/None] Free full body holistic massage
- 0.344 [culture/None] Final Girls Berlin
- 0.340 [music/jazz-blues] Hat Bar Live Jam Sessions

**q12 [semantic_de] Yoga im Park**
- 0.506 [outdoors/None] Mama & Baby Yoga - Postnatales Yoga mit/ohne Baby 0+ mit Cornelia
- 0.455 [meetups/None] momaly walk x BINIBAMBA
- 0.402 [culture/None] Fit im Alter
- 0.402 [culture/None] Fit im Alter
- 0.400 [nightlife/None] Ecstatic Dance & Cacao Journey + Tea & Snacks

**q13 [semantic_en] learn something new workshop**
- 0.487 [meetups/None] Meet the Machines
- 0.433 [meetups/None] Smack My Pitch Up
- 0.426 [meetups/None] CREATIVE SESSION at CIC
- 0.403 [workshops/None] Kiez-Atelier im Studio Bildende Kunst
- 0.399 [culture/None] Einblicke: Workshop zu "Was ihr wollt"

### qwen/qwen3-embedding-8b (dim=4096)

**q01 [semantic_de] Jazzkonzert heute Abend**
- 0.663 [music/jazz-blues] Hat Bar Live Jam Sessions
- 0.624 [nightlife/None] Wet Chikens NEW Material Comedy Mic
- 0.598 [culture/None] SINOPOLIANA. IL LUOGO DEL DESTINO
- 0.532 [music/None] Schüler:innenvorspiel Plus MFEII-Kurs
- 0.528 [meetups/community] Doppelkopf mit Vorkenntnissen

**q02 [semantic_en] jazz concert tonight**
- 0.678 [music/jazz-blues] Hat Bar Live Jam Sessions
- 0.601 [nightlife/None] Wet Chikens NEW Material Comedy Mic
- 0.590 [culture/None] SINOPOLIANA. IL LUOGO DEL DESTINO
- 0.538 [nightlife/None] Perfumed Sundays
- 0.532 [nightlife/None] Ecstatic Dance & Cacao Journey + Tea & Snacks

**q03 [cross_lingual] Flohmarkt am Sonntag**
- 0.732 [markets/flea-market] Ikea Flohmarkt Südkreuz
- 0.636 [family/kids-program] Repaircafé
- 0.596 [food/weekly-market] Wochenmarkt Leopoldplatz
- 0.593 [markets/None] Flowmarkt Schöneberg
- 0.562 [meetups/None] momaly walk x BINIBAMBA

**q04 [cross_lingual] vintage flea market**
- 0.688 [markets/flea-market] Ikea Flohmarkt Südkreuz
- 0.585 [family/kids-program] Repaircafé
- 0.564 [markets/None] Flowmarkt Schöneberg
- 0.547 [nightlife/None] Wet Chikens NEW Material Comedy Mic
- 0.539 [food/weekly-market] Wochenmarkt Leopoldplatz

**q05 [semantic_de] Techno Party in Neukölln**
- 0.784 [nightlife/None] Daytime Berlin Underground Party Tour
- 0.685 [nightlife/None] Ecstatic Dance & Cacao Journey + Tea & Snacks
- 0.669 [nightlife/None] Else x PuMp w Anja Schneider, Hilit Kolet, icykof, Radio Slave, Tal Fu
- 0.653 [nightlife/None] Wet Chikens NEW Material Comedy Mic
- 0.647 [nightlife/None] manic.monda mit Pablo Cornejo (Chile) !FREE ENTRY

**q06 [semantic_en] underground electronic music**
- 0.559 [nightlife/None] TRIG: FROM: TAKE YOUR FREE TICKETS
- 0.556 [nightlife/None] Hypnogogia
- 0.553 [nightlife/None] Daytime Berlin Underground Party Tour
- 0.547 [nightlife/None] TRIG: FROM 23:00 - XXX
- 0.538 [nightlife/None] Perfumed Sundays

**q07 [vibe_no_keyword] etwas Chilliges nach der Arbeit**
- 0.619 [nightlife/None] Wet Chikens NEW Material Comedy Mic
- 0.573 [family/kids-program] Repaircafé
- 0.544 [meetups/community] Nähstübchen
- 0.541 [meetups/None] momaly walk x BINIBAMBA
- 0.512 [nightlife/None] Free full body holistic massage

**q08 [family] etwas mit Kindern unternehmen**
- 0.646 [family/kids-program] Repaircafé
- 0.609 [family/family-event] Bastel-Montag
- 0.596 [family/kids-program] Bastel-Montag
- 0.588 [family/kids-program] Zauberwelt aus Schatten und Figuren
- 0.587 [family/kids-program] DigiQuest

**q09 [family] fun activities for kids**
- 0.630 [family/kids-program] DigiQuest
- 0.613 [family/kids-program] Zauberwelt aus Schatten und Figuren
- 0.608 [nightlife/None] Wet Chikens NEW Material Comedy Mic
- 0.606 [family/kids-program] Bastel-Montag
- 0.601 [family/kids-program] Repaircafé

**q10 [semantic_de] Ausstellung zeitgenössische Kunst**
- 0.552 [nightlife/None] Wet Chikens NEW Material Comedy Mic
- 0.533 [family/kids-program] Repaircafé
- 0.514 [culture/None] faces of mind - Kunst zwischen Sichtbarem und Innerem. Die private Sam
- 0.513 [markets/flea-market] Ikea Flohmarkt Südkreuz
- 0.513 [culture/None] Berlin Business AI Meetup & Professional Networking (Limited Spots)

**q11 [facet_combo] free open air cinema**
- 0.589 [nightlife/None] Wet Chikens NEW Material Comedy Mic
- 0.574 [family/kids-program] Bilderbuchkino mit den Drag Queens Kaey & Vivienne Lovecraft
- 0.569 [meetups/None] momaly walk x BINIBAMBA
- 0.569 [family/kids-program] Repaircafé
- 0.558 [markets/flea-market] Ikea Flohmarkt Südkreuz

**q12 [semantic_de] Yoga im Park**
- 0.587 [nightlife/None] Wet Chikens NEW Material Comedy Mic
- 0.563 [meetups/None] momaly walk x BINIBAMBA
- 0.551 [meetups/community] Nähstübchen
- 0.543 [family/kids-program] Repaircafé
- 0.534 [nightlife/None] Free full body holistic massage

**q13 [semantic_en] learn something new workshop**
- 0.667 [family/kids-program] Repaircafé
- 0.629 [meetups/community] Fortbildung: Kita unterm Regenbogen – sexuelle & geschlechtliche Vielf
- 0.618 [culture/None] Berlin Visit - Scale Your Business with AI – For Business & Startups
- 0.617 [culture/None] Berlin Business AI Meetup & Professional Networking (Limited Spots)
- 0.607 [workshops/None] Umgangssprachliches Ukrainisch / Розмовний клуб для українців

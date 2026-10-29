# TransnetBW Project Radar — quality report

Generated 2026-10-28T16:42:05+00:00 from `iris_staging` · run `c9dc6176-51d0-4123-8015-5d0b9e9dddee` · mode **live** · status **succeeded** (exit 0) · code `097f2b6`

## Source verification

Facts checked by hand on 2026-10-27 — this run: listing 23 cards, sitemap 948 URLs, press feed 563 items.

- The brief's URL https://www.transnetbw.de/de/netzentwicklung answers HTTP 303 and lands on /de/netzentwicklung/planung/netzentwicklungsplan, an overview without project data.
- The project catalogue is /de/netzentwicklung/projekte/alle-projekte: server-rendered HTML, one page, no pagination; its map is a schematic SVG without coordinates.
- robots.txt disallows only /neos/.
- /de/sitemap.xml gives a lastmod for every URL; listing and sitemap disagree on three projects.
- Project pages carry no publication date and no coordinates.
- The newsroom list is rendered by JavaScript from /de/api/press-releases (JSON, 564 entries from 2009-10-15 to 2026-10-15, one URL listed twice); article pages state their date as text ("15. Oktober 2026").
- The newsroom CMS reuses URL slugs for unrelated articles (e.g. …-umspannwerkes-wendlingen-1 is a release on the underground-cable priority); the URL is a stable identifier, the page title is authoritative.

## Records

120 staged records (0 retired), 11 held for review.

| by kind | records |
|---|---|
| press_release | 97 |
| project | 23 |

| by signal type | records |
|---|---|
| grid_capacity_constraint | 75 |
| transformer_modernization | 45 |

| by stage | records |
|---|---|
| approval | 48 |
| construction | 44 |
| in_operation | 11 |
| planning | 1 |
| unknown | 16 |

## Quality gates

| gate | value | required | passed |
|---|---|---|---|
| discovery_gap | 3 | <= 5 | yes |
| listing_cards | 23 | >= 15 | yes |
| resolved_rows | 52 | >= 1 | yes |
| fetch_failure_ratio | 0.0 | <= 0.3 | yes |

## Unresolved and ambiguous locations

Points are EPSG:25832. ambiguous: 22, resolved: 52, unresolved: 46 · precision municipality: 6, substation: 46

| record | status | named | reason |
|---|---|---|---|
| press:alle-suedlink-abschnitte-in-der-genehmigung-transnetbw-reicht-letzte-planfeststellungsunterlagen-in-niedersachsen-ein | unresolved | — | no station named in title, subheads or lead; the linked project has no location either |
| press:baustart-fuer-suedlink-in-baden-wuerttemberg | unresolved | — | no station named in title, subheads or lead; the linked project has no location either |
| press:baustart-ultranet-im-bauabschnitt-b1 | unresolved | — | no station named in title, subheads or lead; the linked project has no location either |
| press:bundesweit-laufen-auf-allen-suedlink-baustellen-die-arbeiten-weiterhin-mit-hochdruck | unresolved | — | no station named in title, subheads or lead; the linked project has no location either |
| press:bwihk-stromstudie-2024-unterstreicht-die-dringlichkeit-des-stromnetzausbaus | unresolved | — | no station or line ends named in title, subheads or lead, and no linked project |
| press:effizienteres-engpassmanagement-uebertragungsnetzbetreiber-nehmen-redispatch-abwicklungsserver-ras-in-betrieb | unresolved | — | no station or line ends named in title, subheads or lead, and no linked project |
| press:energiewende-monitoringbericht | unresolved | — | no station or line ends named in title, subheads or lead, and no linked project |
| press:erdkabelbericht-zieht-zwischenbilanz | unresolved | — | no station or line ends named in title, subheads or lead, and no linked project |
| press:es-geht-voran-erdkabel-fuer-suedlink-gehen-in-produktion | unresolved | — | no station named in title, subheads or lead; the linked project has no location either |
| press:feierlicher-baustart-von-suedlink | unresolved | — | no station named in title, subheads or lead; the linked project has no location either |
| press:hoeherauslastung-der-stromleitungen-hilft-im-winter | unresolved | — | no station or line ends named in title, subheads or lead, and no linked project |
| press:hydrogreen-boost-studie-bestaetigt-wirtschaftlichkeit-und-grosses-potenzial-fur-hybride-netzbooster | unresolved | — | no station or line ends named in title, subheads or lead, and no linked project |
| press:kleinstflexibilitaeten-als-beitrag-fuer-das-netzengpassmanagement | unresolved | — | no station or line ends named in title, subheads or lead, and no linked project |
| press:leitungsbauprojekt-zwischen-birkenfeld-und-punkt-oetisheim-transnetbw-erhaelt-planfeststellungsbeschluss | ambiguous | Birkenfeld, Ötisheim | line between two places: no single representative point |
| press:letzte-genehmigungsphase-fuer-suedlink-in-baden-wuerttemberg-transnetbw-reicht-planfeststellungsunterlagen-im-raum-heilbronn-franken-ein | unresolved | — | no station named in title, subheads or lead; the linked project has no location either |
| press:mastbau-zur-netzverstaerkung-zwischen-karlsruhe-daxlanden-und-eichstetten-am-kaiserstuhl-beginnt | ambiguous | Karlsruhe-Daxlanden, Eichstetten | line between two places: no single representative point |
| press:naechster-schritt-der-realisierung-regionale-suedlink-planungsbueros-nehmen-arbeit-auf | unresolved | — | no station named in title, subheads or lead; the linked project has no location either |
| press:netzbauprojekt-rippolingen-istein-transnetbw-modernisiert-zwei-leitungsanlagen-in-den-landkreisen-loerrach-und-waldshut | ambiguous | Rippolingen, Istein | linked project has no single representative point |
| press:startschuss-fuer-witterungsabhaengigen-freileitungsbetrieb-3-0 | unresolved | — | no station or line ends named in title, subheads or lead, and no linked project |
| press:suedlink-auftrag-fuer-kunststoffisolierte-525-kilovolt-erdkabel-vergeben | unresolved | — | no station named in title, subheads or lead; the linked project has no location either |
| press:suedlink-auftrag-fuer-zwei-konverteranlagen-vergeben | unresolved | — | no station named in title, subheads or lead; the linked project has no location either |
| press:suedlink-bauarbeiten-im-bergwerk-und-kampfmitteluntersuchungen-gestartet | unresolved | — | no station named in title, subheads or lead; the linked project has no location either |
| press:suedlink-bau-im-nordosten-baden-wuerttembergs-kann-starten | unresolved | — | no station named in title, subheads or lead; the linked project has no location either |
| press:suedlink-bau-in-suedniedersachsen-kann-starten | unresolved | — | no station named in title, subheads or lead; the linked project has no location either |
| press:suedlink-einigung-mit-bauernverbaenden-ueber-entschaedigung | unresolved | — | no station named in title, subheads or lead; the linked project has no location either |
| press:suedlink-erste-gleichstrom-erdkabel-erreichen-zwischenlager | unresolved | — | no station named in title, subheads or lead; the linked project has no location either |
| press:suedlink-geht-auch-in-suedniedersachsen-in-den-bau | unresolved | — | no station named in title, subheads or lead; the linked project has no location either |
| press:suedlink-im-gesamten-verlauf-in-der-planfeststellung-transnetbw-reicht-planfeststellungsantrag-fuer-das-leinetal-ein | unresolved | — | no station named in title, subheads or lead; the linked project has no location either |
| press:suedlink-kommt-transnetbw-reicht-planfeststellungsunterlagen-fuer-nordhessen-ein | unresolved | — | no station named in title, subheads or lead; the linked project has no location either |
| press:suedlink-kommt-transnetbw-reicht-planfeststellungsunterlagen-fuer-suedniedersachsen-ein | unresolved | — | no station named in title, subheads or lead; the linked project has no location either |
| press:suedlink-kommt-transnetbw-reicht-planfeststellungsunterlagen-fuer-unterfranken-ein | unresolved | — | no station named in title, subheads or lead; the linked project has no location either |
| press:suedlink-kommt-transnetbw-reicht-planfeststellungsunterlagen-fuer-west-und-suedthueringen-ein | unresolved | — | no station named in title, subheads or lead; the linked project has no location either |
| press:suedlink-kommt-voran-transnetbw-leitet-letzte-phase-des-genehmigungsverfahrens-ein-und-schafft-grundlage-fuer-spaeteren-bau | unresolved | — | no station named in title, subheads or lead; the linked project has no location either |
| press:suedlink-letzte-abschnitte-genehmigt | unresolved | — | no station named in title, subheads or lead; the linked project has no location either |
| press:suedlink-planfeststellungsantrag-fuer-thueringen-und-den-noerdlichen-teil-unterfrankens-eingereicht | unresolved | — | no station named in title, subheads or lead; the linked project has no location either |
| press:suedlink-schacht-arbeiten-fuer-bergwerks-abschnitt-beauftragt | unresolved | — | no station named in title, subheads or lead; the linked project has no location either |
| press:suedlink-tennet-und-transnetbw-begruessen-festgelegten-verlauf | unresolved | — | no station named in title, subheads or lead; the linked project has no location either |
| press:suedlink-tiefbau-arbeiten-in-baden-wuerttemberg-vergeben | unresolved | — | no station named in title, subheads or lead; the linked project has no location either |
| press:transnetbw-informierte-in-merdingen | ambiguous | Eichstetten, Bundesgrenze Frankreich | linked project has no single representative point |
| press:transnetbw-informierte-in-merdingen-1 | unresolved | — | no station named in title, subheads or lead; the linked project has no location either |
| press:transnetbw-modernisiert-hoechstspannungsleitung-zwischen-herbertingen-und-hoheneck | ambiguous | Herbertingen, Hoheneck | line between two places: no single representative point |
| press:transnetbw-reicht-planfeststellungsantraege-fuer-den-suedlichsten-suedlink-abschnitt-ein | unresolved | — | no station named in title, subheads or lead; the linked project has no location either |
| press:transnetbw-reicht-suedlink-planfeststellungsantrag-fuer-suedlichen-teil-unterfrankens-ein | unresolved | — | no station named in title, subheads or lead; the linked project has no location either |
| press:transnetbw-reicht-suedlink-planfeststellungsantrag-fuer-suedniedersachsen-und-hessen-ein | unresolved | — | no station named in title, subheads or lead; the linked project has no location either |
| press:transnetbw-startet-mit-dem-neubau-der-380-kilovolt-leitung-zwischen-birkenfeld-und-oetisheim | ambiguous | Birkenfeld, Ötisheim | line between two places: no single representative point |
| press:transnetbw-treibt-planfeststellung-bei-netzverstaerkungsprojekt-zwischen-gaukoenigshofen-und-kupferzell-voran | ambiguous | Gaukönigshofen, Kupferzell | line between two places: no single representative point |
| press:transnetbw-und-netze-bw-staerken-gemeinsam-oekologisches-trassenmanagement | unresolved | — | no station or line ends named in title, subheads or lead, and no linked project |
| press:transnetbw-und-tennet-germany-feiern-symbolische-inbetriebnahme-der-netzverstaerkung-grafenrheinfeld-kupferzell-grossgartach | ambiguous | Grafenrheinfeld, Großgartach | several stations named: no single representative point |
| press:transnetbw-und-uni-hohenheim-untersuchen-einfluss-von-erdkabeln-auf-boeden-und-pflanzen | unresolved | — | no station named in title, subheads or lead; the linked project has no location either |
| press:uebertragungsnetzbetreiber-veroeffentlichen-ersten-entwurf-des-netzentwicklungsplans-2037-2045 | unresolved | — | no station or line ends named in title, subheads or lead, and no linked project |
| press:ultranet-transnetbw-erreicht-meilenstein-im-genehmigungsverfahren | ambiguous | Mannheim-Wallstadt, Philippsburg | line between two places: no single representative point |
| press:ultranet-transnetbw-informiert-ueber-planungsstand | unresolved | — | no station named in title, subheads or lead; the linked project has no location either |
| press:umsetzung-startet-genehmigung-fuer-laengsten-teilabschnitt-der-netzverstaerkung-badische-rheinschiene-erteilt | ambiguous | Daxlanden, Weier | several stations named: no single representative point |
| press:umspannwerke-gurtweil-tiengen-amprion-und-transnetbw-bleiben-im-tal | ambiguous | Gurtweil, Tiengen | several stations named: no single representative point |
| press:wir-brauchen-suedlink | unresolved | — | no station named in title, subheads or lead; the linked project has no location either |
| project:380-kv-netzverstaerkung-mittlerer-neckarraum | ambiguous | Mittlerer Neckarraum | line or area project: no single representative point |
| project:birkenfeld-punkt-oetisheim | ambiguous | Birkenfeld, Ötisheim | line or area project: no single representative point |
| project:eichstetten-bundesgrenze-frankreich | ambiguous | Eichstetten, Bundesgrenze Frankreich | line or area project: no single representative point |
| project:grafenrheinfeld-kupferzell-grossgartach | ambiguous | Grafenrheinfeld, Kupferzell, Großgartach | line or area project: no single representative point |
| project:hochrhein | ambiguous | Herbertingen, Waldshut-Tiengen | line or area project: no single representative point |
| project:netzverstaerkung-badische-rheinschiene | ambiguous | Badische Rheinschiene | line or area project: no single representative point |
| project:netzverstaerkung-neckar-odenwald | ambiguous | Neckar-Odenwald | line or area project: no single representative point |
| project:netzverstaerkung-reicheneck-rommelsbach | ambiguous | Reicheneck, Rommelsbach | line or area project: no single representative point |
| project:netzverstaerkung-weinheim-karlsruhe | ambiguous | Weinheim, Karlsruhe | line or area project: no single representative point |
| project:rippolingen-istein | ambiguous | Rippolingen, Istein | line or area project: no single representative point |
| project:stalldorf-main-tauber | ambiguous | Stalldorf | line or area project: no single representative point |
| project:suedlink | unresolved | — | no place named in the title |
| project:ultranet | unresolved | — | no place named in the title |

## Publication dates

97 of 97 press-release dates confirmed by both the article page and the feed.

Project pages state no publication date: `published_at` is NULL for projects by design; `source_last_modified` carries the sitemap lastmod.

## Exclusions

| reason | record | evidence |
|---|---|---|
| outside_bw | press:baustart-fur-suedlink-in-bayern | the title places the release outside Baden-Württemberg |
| out_of_scope_no_signal | press:einsatz-in-luftiger-hoehe-leitungsinspektion-per-hubschrauber | not loaded: out of scope no signal |
| out_of_scope_policy | press:Freileitungsvorrang-konsequent-umsetzen | Freileitungsvorrang konsequent umsetzen: Breites Bündnis fordert Nachbesserungen am Bundesbedarfsplangesetz |
| out_of_scope_policy | press:freileitungsvorrang-staerkt-netzausbau-einschraenkungen-schaffen-unsicherheit | Freileitungsvorrang stärkt Netzausbau – Einschränkungen schaffen Unsicherheit |
| outside_bw | press:offizieller-bauauftakt-fuer-suedlink-in-hessen-netzausbau-macht-grosse-fortschritte | the title places the release outside Baden-Württemberg |
| outside_bw | press:suedlink-bau-in-bayern-kann-starten | the title places the release outside Baden-Württemberg |
| outside_bw | press:suedlink-bau-in-hessen-kann-starten | the title places the release outside Baden-Württemberg |
| outside_bw | press:suedlink-erste-tiefbau-arbeiten-in-unterfranken-vergeben | the title places the release outside Baden-Württemberg |
| out_of_scope_back_office | press:transnetbw-nimmt-neue-loesung-fuer-die-abrechnungspruefung-im-engpass-management-in-betrieb | TransnetBW nimmt neue Lösung für die Abrechnungsprüfung im Engpass-Management in Betrieb |
| out_of_scope_policy | press:transnetbw-startet-um-und-neubau-des-umspannwerkes-wendlingen-1 | Expertenkommission rät zur Überprüfung des Erdkabelvorrangs |
| out_of_scope_no_signal | press:umweltminister-franz-untersteller-besucht-transnetbw-hauptschaltleitung | not loaded: out of scope no signal |
| out_of_scope_maintenance | project:seiltausch-hoellental | Seiltausch Höllental (LA5120) willkommen im projekt |
| outside_bw | project:umspannwerk-stalldorf | Stalldorf (Umspannwerk Stalldorf) lies outside Baden-Württemberg |

## Listing and sitemap differences

| difference | project |
|---|---|
| listing_only | project:stalldorf-main-tauber |
| sitemap_only | project:schaltanlage-obermooweiler |
| sitemap_only | project:seiltausch-hoellental |

## Review queue

| record | title | reasons |
|---|---|---|
| press:bwihk-stromstudie-2024-unterstreicht-die-dringlichkeit-des-stromnetzausbaus | BWIHK-Stromstudie 2024 unterstreicht die Dringlichkeit des Stromnetzausbaus | no_project_and_no_location |
| press:effizienteres-engpassmanagement-uebertragungsnetzbetreiber-nehmen-redispatch-abwicklungsserver-ras-in-betrieb | Effizienteres Engpassmanagement: Übertragungsnetzbetreiber nehmen Redispatch-Abwicklungsserver (RAS) in Betrieb | no_project_and_no_location |
| press:energiewende-monitoringbericht | Der Netzausbau ist ein wichtiger Schlüssel für die Energiewende | no_project_and_no_location |
| press:erdkabelbericht-zieht-zwischenbilanz | Erdkabelbericht zieht Zwischenbilanz | no_project_and_no_location |
| press:hoeherauslastung-der-stromleitungen-hilft-im-winter | Höherauslastung der Stromleitungen hilft im Winter | no_project_and_no_location |
| press:hydrogreen-boost-studie-bestaetigt-wirtschaftlichkeit-und-grosses-potenzial-fur-hybride-netzbooster | HydrogREenBoost: Studie bestätigt Wirtschaftlichkeit und großes Potenzial für hybride Netzbooster | no_project_and_no_location |
| press:kleinstflexibilitaeten-als-beitrag-fuer-das-netzengpassmanagement | Kleinstflexibilitäten als Beitrag für das Netzengpassmanagement | no_project_and_no_location |
| press:netzbauprojekt-rippolingen-istein-transnetbw-modernisiert-zwei-leitungsanlagen-in-den-landkreisen-loerrach-und-waldshut | Netzbauprojekt Rippolingen – Istein: Transnet BW modernisiert zwei Leitungsanlagen in den Landkreisen Lörrach und Waldshut | low_confidence_classification |
| press:startschuss-fuer-witterungsabhaengigen-freileitungsbetrieb-3-0 | Startschuss für witterungsabhängigen Freileitungsbetrieb 3.0 - TransnetBW und energy & meteo systems legen rund 300 Standorte zur echtzeitfähigen Erfassung der Belastbarkeit von Freileitungen fest | no_project_and_no_location |
| press:transnetbw-und-netze-bw-staerken-gemeinsam-oekologisches-trassenmanagement | TransnetBW und Netze BW stärken gemeinsam Ökologisches Trassenmanagement | no_project_and_no_location |
| press:uebertragungsnetzbetreiber-veroeffentlichen-ersten-entwurf-des-netzentwicklungsplans-2037-2045 | Bürgerdialog informiert Bürgerschaft in Oberjettingen zur geplanten Erweiterung und zumNeubau des örtlichen Umspannwerks | no_project_and_no_location |

## Issues of this run

| severity | code | count |
|---|---|---|
| info | duplicate_in_feed | 1 |
| info | excluded_out_of_scope_back_office | 1 |
| info | excluded_out_of_scope_maintenance | 1 |
| info | excluded_out_of_scope_no_signal | 2 |
| info | excluded_out_of_scope_policy | 3 |
| info | excluded_outside_bw | 6 |
| info | location_ambiguous | 22 |
| warning | discovery_listing_only | 1 |
| warning | discovery_sitemap_only | 2 |
| warning | location_unresolved | 46 |


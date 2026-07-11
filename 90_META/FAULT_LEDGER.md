# FAULT LEDGER

One line per fault. Scan before technical work on a tagged topic.

- [ABSOLUTE_ZERO][project,faults,absolute-zero] prompt-compiler changeset committed while `verifier.py check` -> verifier now exempts `ARTIFACT_DIRS` (mirrors indexer ([[debugging-silent-failures]])
- [ASUNAMA][project,faults,drone] empty white Kit viewport, "not responding", every colored spawn. -> bind materials USD-natively (`_bind_material` via `UsdShade`); drop ([[debugging-silent-failures]])
- [ASUNAMA][project,faults,drone] `data_generator` stuck forever; kit log stops after "Replicator Step". -> drop the orchestrator; tick `simulation_app.update()` a bounded ([[debugging-silent-failures]])
- [ASUNAMA][project,faults,drone] drone explores but Return-To-Home never registers arrival. -> measure distance to base_station in the absolute frame. ([[gps-denied-localization]])
- [ASUNAMA][project,faults,drone] rocks stacked on streaks/soil; markers buried in renders. -> return `None` on exhaustion; every caller skips; largest-footprint-first. ([[coverage-planning]])
- [ASUNAMA][project,faults,drone] exploration plateaus under acceptance threshold. -> `mark_explored_footprint(x,y,radius)` gated on pose confidence. ([[coverage-planning]])

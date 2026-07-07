cd /c/Users/Ashu/Documents/wakewordprod/wakeword_datagen
for i in $(seq 1 8); do
  before=$(ls output/negatives | grep -c kokoro)
  echo "=== attempt $i, kokoro_neg_before=$before ==="
  ./venvs/kokoro/Scripts/python.exe gen_kokoro.py >> gen_kokoro.log 2>&1
  rc=$?
  after=$(ls output/negatives | grep -c kokoro)
  echo "=== attempt $i rc=$rc kokoro_neg_after=$after ==="
  if grep -aq "\[DONE\]" gen_kokoro.log && [ $rc -eq 0 ]; then echo "COMPLETED_CLEAN"; break; fi
  if [ "$after" = "$before" ]; then echo "NO_PROGRESS_STOP (poison input at position after $after)"; break; fi
done
echo "RESUME_LOOP_END kokoro_neg=$(ls output/negatives | grep -c kokoro)"

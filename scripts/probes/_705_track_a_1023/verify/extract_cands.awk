BEGIN{FS="\t";OFS="\t"}
NR==1{for(i=1;i<=NF;i++)c[$i]=i; print "ticker","D","E","K","pole_date","retrigger","retrigger_chain","base_id","split","C1"; next}
{ if($c["split"]!=want){ nd++; next }
  if($c["D"]>cut || $c["E"]>cut){ na++; next }
  print $c["ticker"],$c["D"],$c["E"],$c["K"],$c["pole_date"],$c["retrigger"],$c["retrigger_chain"],$c["base_id"],$c["split"],$c["C1"]; kept++ }
END{print "dropped_not_want=" nd+0 " dropped_after_cut=" na+0 " kept=" kept+0 > "/dev/stderr"}

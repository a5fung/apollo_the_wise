BEGIN{FS="\t";OFS="\t"}
NR==1{for(i=1;i<=NF;i++)c[$i]=i; print "ticker","watch_date","split","pole_date","pivot_tl_date","C0_tl"; next}
{ if($c["split"]!=want){ nd++; next }
  if($c["watch_date"]>cut){ na++; next }
  print $c["ticker"],$c["watch_date"],$c["split"],$c["pole_date"],$c["pivot_tl_date"],$c["C0_tl"]; kept++ }
END{print "dropped_not_want=" nd+0 " dropped_after_cut=" na+0 " kept=" kept+0 > "/dev/stderr"}

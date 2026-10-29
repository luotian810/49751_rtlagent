`timescale 1ns/1ps
module tb;
  reg completed=0;
  reg clk=0,reset=1,en=0,bit_in=0;wire md,mr;
  integer errors=0,samples=0,i,len=0;
  reg accepted_bits[0:2047];
  reg expected;reg [31:0] rng=32'h23456789;
  TopModule dut(.*,.match(md));
  RefModule refm(.*,.match(mr));
  always #5 clk=~clk;
  task step(input bit r,e,b);
    begin
      @(negedge clk);reset=r;en=e;bit_in=b;
      @(posedge clk);expected=0;
      if(r) len=0;
      else if(e) begin
        accepted_bits[len]=b;len=len+1;
        if(len>=3) expected=accepted_bits[len-3]&&!accepted_bits[len-2]&&accepted_bits[len-1];
      end
      #1;if(mr !== expected) $fatal(1,"ORACLE_ERROR pattern");
      samples=samples+1;if(md !== mr) errors=errors+1;
    end
  endtask
  initial begin
    @(posedge clk);#1;
    step(0,1,1);step(0,1,0);step(0,1,1);
    step(0,0,0);step(0,0,1);step(0,1,0);step(0,1,1);
    step(1,1,1);step(0,1,0);step(0,1,1);
    for(i=0;i<768;i=i+1) begin
      rng=1664525*rng+1013904223;
      step(rng[30:26]==0,rng[24:23]!=0,rng[22]);
    end
    completed=1;$finish;
  end
  final begin
    // Only a complete stimulus sequence can produce a valid result.
    if(completed) begin
    $display("Hint: Total mismatched samples is %0d out of %0d samples", errors, samples);
    $display("Mismatches: %0d in %0d samples", errors, samples);
    end else $display("TIMEOUT fixture incomplete");
  end
  initial begin #1000000; $fatal(1,"TIMEOUT fixture watchdog"); end
endmodule

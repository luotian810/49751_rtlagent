`timescale 1ns/1ps
module tb;
  reg completed=0;
  reg clk=0,reset=1,load=0,en=0;
  reg [4:0] data=0;
  wire [4:0] qd,qr;
  integer errors=0,samples=0,i,expected=0;
  reg [31:0] rng=32'h13579bdf;
  TopModule dut(.*,.q(qd));
  RefModule refm(.*,.q(qr));
  always #5 clk=~clk;
  task step(input bit r,l,e,input [4:0] d);
    reg [4:0] old_q;
    begin
      @(negedge clk); old_q=qr;reset=r;load=l;en=e;data=d;
      // Catch asynchronous reset implementations before the active edge.
      #1; samples=samples+1;
      if(qd !== old_q) errors=errors+1;
      @(posedge clk);
      if(r) expected=0;else if(l) expected=d;else if(e) expected=(expected+1)%32;
      #1;
      if(qr !== expected[4:0]) $fatal(1,"ORACLE_ERROR counter");
      samples=samples+1;if(qd !== qr) errors=errors+1;
    end
  endtask
  initial begin
    @(posedge clk);#1;
    step(0,1,0,31);step(0,0,1,0);step(0,0,0,7);
    step(0,1,1,9);step(1,1,1,23);step(0,1,0,17);
    // Asserting reset between edges must not immediately erase nonzero q.
    step(1,0,0,0);
    for(i=0;i<512;i=i+1) begin
      rng=1664525*rng+1013904223;
      step(rng[28:25]==0,rng[24:23]==0,rng[22],rng[4:0]);
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

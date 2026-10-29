`timescale 1ns/1ps
module tb;
  reg completed=0;
  reg clk=0,reset=1,accept=0;reg [3:0] req=0;wire [3:0] gd,gr;
  integer errors=0,samples=0,i,j,pointer=0,selected;
  reg [3:0] expected;reg [31:0] rng=32'h10203040;
  TopModule dut(.*,.grant(gd));
  RefModule refm(.*,.grant(gr));
  always #5 clk=~clk;
  task check;
    integer k;
    begin
      selected=-1;expected=0;
      for(k=3;k>=0;k=k-1)
        if(req[(pointer+k)%4]) selected=(pointer+k)%4;
      if(selected>=0) expected=4'b0001<<selected;
      if(gr !== expected) $fatal(1,"ORACLE_ERROR arbiter");
      samples=samples+1;if(gd !== gr) errors=errors+1;
    end
  endtask
  task step(input bit r,a,input [3:0] requests);
    begin
      @(negedge clk);reset=r;accept=a;req=requests;#1;check;
      @(posedge clk);
      if(r) pointer=0;else if(a && selected>=0) pointer=(selected+1)%4;
      #1;check;
    end
  endtask
  initial begin
    @(posedge clk);#1;
    repeat(8) step(0,1,15);
    repeat(4) step(0,0,15);
    step(0,1,0);step(0,1,0);step(0,0,15);step(1,1,15);
    // All request masks from several pointer states, with and without acceptance.
    for(i=0;i<16;i=i+1) begin step(0,0,i);step(0,1,i);end
    for(j=0;j<512;j=j+1) begin
      rng=1664525*rng+1013904223;
      step(rng[30:26]==0,rng[24],rng[23:20]);
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

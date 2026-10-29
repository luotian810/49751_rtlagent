`timescale 1ns/1ps
module tb;
  reg completed=0;
  reg clk=0,reset=1,in_valid=0,out_ready=0;
  reg [7:0] in_data=0;
  wire rd,vd,rr,vr;wire [7:0] dd,dr;
  integer errors=0,samples=0,i;
  reg [31:0] rng=32'h8badf00d;
  reg occupied=0;reg [7:0] stored=0;
  TopModule dut(.*,.in_ready(rd),.out_valid(vd),.out_data(dd));
  RefModule refm(.*,.in_ready(rr),.out_valid(vr),.out_data(dr));
  always #5 clk=~clk;
  task check;
    begin
      if({rr,vr,dr} !== {(!occupied || out_ready),occupied,(occupied?stored:8'h00)})
        $fatal(1,"ORACLE_ERROR elastic buffer");
      samples=samples+1;if({rd,vd,dd} !== {rr,vr,dr}) errors=errors+1;
    end
  endtask
  task step(input bit r,v,o,input [7:0] d);
    begin
      @(negedge clk);reset=r;in_valid=v;out_ready=o;in_data=d;#1;check;
      @(posedge clk);
      if(r) begin occupied=0;stored=0;end
      else if(!occupied || o) begin occupied=v;if(v) stored=d;end
      #1;check;
    end
  endtask
  initial begin
    @(posedge clk);#1;
    step(0,1,0,8'h11);step(0,1,0,8'h22);step(0,0,0,8'h33);
    step(0,1,1,8'h44);step(0,1,1,8'h55);step(0,0,1,8'h66);
    step(0,1,1,8'h77);step(1,1,1,8'h88);step(0,0,0,0);
    for(i=0;i<512;i=i+1) begin
      rng=1664525*rng+1013904223;
      step(rng[28:25]==0,rng[24],rng[23],rng[7:0]);
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

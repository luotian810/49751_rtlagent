`timescale 1ns/1ps
module tb;
  reg completed=0;
  reg signed [7:0] a,b;
  wire signed [7:0] yd,yr;
  wire sd,sr;
  integer i,j,expected,errors=0,samples=0;
  TopModule dut(.a(a),.b(b),.y(yd),.saturated(sd));
  RefModule refm(.a(a),.b(b),.y(yr),.saturated(sr));
  initial begin
    // Exhaust all 65,536 signed input pairs, including both exact boundaries.
    for(i=-128;i<128;i=i+1) for(j=-128;j<128;j=j+1) begin
      a=i;b=j;#1;
      expected=i+j;
      if (yr !== ((expected>127)?8'sd127:(expected < -128)?8'sh80:expected[7:0])
          || sr !== ((expected>127)||(expected < -128)))
        $fatal(1,"ORACLE_ERROR signed saturation");
      samples=samples+1;
      if({yd,sd} !== {yr,sr}) errors=errors+1;
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

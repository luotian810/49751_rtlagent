`timescale 1ns/1ps
module tb;
 reg completed=0;
 reg signed [5:0] lhs_i,rhs_i;
 reg subtract_i;
 wire signed [5:0] yd,yr;
 wire cd,cr;
 reg [5:0] expected;
 reg clip;
 integer errors=0,samples=0,a,b,s,z;
 TopModule dut(.lhs_i(lhs_i),.rhs_i(rhs_i),.subtract_i(subtract_i),.value_o(yd),.clipped_o(cd));
 RefModule refm(.lhs_i(lhs_i),.rhs_i(rhs_i),.subtract_i(subtract_i),.value_o(yr),.clipped_o(cr));
 initial begin
   for(a=-32;a<32;a=a+1) for(b=-32;b<32;b=b+1) for(s=0;s<2;s=s+1) begin
     lhs_i=a;rhs_i=b;subtract_i=s;
     z=s ? a-b : a+b;clip=(z>31)||(z< -32);
     if(z>31) expected=31;else if(z< -32) expected=32;else expected=z;
     #1;
     if({yr,cr}!=={expected,clip}) $fatal(1,"ORACLE_ERROR sat6 a=%0d b=%0d sub=%0d",a,b,s);
     samples=samples+1;
     if({yd,cd}!=={expected,clip}) begin
       errors=errors+1;
       if(errors==1) $display("FIRST_MISMATCH lhs=%0d rhs=%0d subtract=%0d got=%0d/%b expected=%0d/%b",a,b,s,yd,cd,$signed(expected),clip);
     end
   end
   completed=1;$finish;
 end

  final begin
    if(completed) begin
      $display("Hint: Total mismatched samples is %0d out of %0d samples",errors,samples);
      $display("Mismatches: %0d in %0d samples",errors,samples);
    end else $display("TIMEOUT fixture incomplete");
  end
  initial begin #1000000; $fatal(1,"TIMEOUT fixture watchdog"); end
endmodule

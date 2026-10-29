`timescale 1ns/1ps
module tb;
 reg completed=0;
 reg clock_i=0,reset_i=1,bit_enable_i=0,bit_i=0;
 wire md,mr;
 integer errors=0,samples=0,i,j,n=0;
 reg accepted_bits[0:2047];
 reg expected=0;
 reg [31:0] rng=32'h23e8a5b7;
 TopModule dut(.clock_i(clock_i),.reset_i(reset_i),.bit_enable_i(bit_enable_i),.bit_i(bit_i),.match_o(md));
 RefModule refm(.clock_i(clock_i),.reset_i(reset_i),.bit_enable_i(bit_enable_i),.bit_i(bit_i),.match_o(mr));
 always #5 clock_i=~clock_i;
 task check;
   begin
     if(mr!==expected) $fatal(1,"ORACLE_ERROR pattern1101");
     samples=samples+1;
     if(md!==expected) begin
       errors=errors+1;
       if(errors==1) $display("FIRST_MISMATCH step=%0d reset=%b enable=%b bit=%b got=%b expected=%b",samples,reset_i,bit_enable_i,bit_i,md,expected);
     end
   end
 endtask
 task step(input r,e,b);
   begin
     @(negedge clock_i);reset_i=r;bit_enable_i=e;bit_i=b;
     #1;check;
     @(posedge clock_i);
     expected=0;
     if(r) n=0;
     else if(e) begin
       accepted_bits[n]=b;n=n+1;
       if(n>=4) expected=accepted_bits[n-4] && accepted_bits[n-3] && !accepted_bits[n-2] && accepted_bits[n-1];
     end
     #1;check;
   end
 endtask
 initial begin
   @(posedge clock_i);#1;check;
   // 1101101 has overlapping matches; pauses must clear only the pulse.
   step(0,1,1);step(0,1,1);step(0,1,0);step(0,1,1);
   step(0,0,0);step(0,0,1);step(0,1,1);step(0,1,0);step(0,1,1);
   for(i=0;i<64;i=i+1) begin
     step(1,0,0);
     for(j=5;j>=0;j=j-1) begin step(0,1,(i>>j)&1);step(0,0,1);end
   end
   for(i=0;i<500;i=i+1) begin
     rng=1664525*rng+1013904223;
     step(rng[31:27]==0,rng[8],rng[0]);
   end
   step(1,1,1);step(0,0,0);completed=1;$finish;
 end

  final begin
    if(completed) begin
      $display("Hint: Total mismatched samples is %0d out of %0d samples",errors,samples);
      $display("Mismatches: %0d in %0d samples",errors,samples);
    end else $display("TIMEOUT fixture incomplete");
  end
  initial begin #1000000; $fatal(1,"TIMEOUT fixture watchdog"); end
endmodule

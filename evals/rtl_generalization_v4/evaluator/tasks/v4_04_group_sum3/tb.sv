`timescale 1ns/1ps
module tb;
 reg completed=0;
 reg clk_i=0,reset_i=1,sample_valid_i=0;
 reg [4:0] sample_i=0;
 wire [6:0] sd,sr;
 wire vd,vr;
 integer errors=0,samples=0,i,n=0,total=0,last=0;
 reg pulse=0;
 reg [31:0] rng=32'hd90f5371;
 TopModule dut(.clk_i(clk_i),.reset_i(reset_i),.sample_valid_i(sample_valid_i),.sample_i(sample_i),.sum_o(sd),.sum_valid_o(vd));
 RefModule refm(.clk_i(clk_i),.reset_i(reset_i),.sample_valid_i(sample_valid_i),.sample_i(sample_i),.sum_o(sr),.sum_valid_o(vr));
 always #5 clk_i=~clk_i;
 task check;
   begin
     if({sr,vr}!=={last[6:0],pulse}) $fatal(1,"ORACLE_ERROR group sum");
     samples=samples+1;
     if({sd,vd}!=={last[6:0],pulse}) begin
       errors=errors+1;
       if(errors==1) $display("FIRST_MISMATCH step=%0d reset=%b sample_valid=%b sample=%0d got=%0d/%b expected=%0d/%b",samples,reset_i,sample_valid_i,sample_i,sd,vd,last,pulse);
     end
   end
 endtask
 task step(input r,v,input [4:0] d);
   begin
     @(negedge clk_i);reset_i=r;sample_valid_i=v;sample_i=d;
     #1;check;
     @(posedge clk_i);
     pulse=0;
     if(r) begin n=0;total=0;last=0;end
     else if(v) begin
       total=total+d;n=n+1;
       if(n==3) begin last=total;pulse=1;n=0;total=0;end
     end
     #1;check;
   end
 endtask
 initial begin
   @(posedge clk_i);#1;check;
   step(0,1,7);step(0,0,31);step(0,1,9);step(0,1,13);
   for(i=0;i<9;i=i+1) step(0,1,31);
   step(0,1,11);step(1,1,31);step(0,1,1);step(0,1,2);step(0,1,3);
   for(i=0;i<500;i=i+1) begin
     rng=1664525*rng+1013904223;
     step(rng[31:27]==0,rng[8],rng[4:0]);
   end
   step(1,0,0);step(0,0,0);completed=1;$finish;
 end

  final begin
    if(completed) begin
      $display("Hint: Total mismatched samples is %0d out of %0d samples",errors,samples);
      $display("Mismatches: %0d in %0d samples",errors,samples);
    end else $display("TIMEOUT fixture incomplete");
  end
  initial begin #1000000; $fatal(1,"TIMEOUT fixture watchdog"); end
endmodule

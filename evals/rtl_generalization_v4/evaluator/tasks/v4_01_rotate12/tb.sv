`timescale 1ns/1ps
module tb;
 reg completed=0;
 reg [11:0] word_i;
 reg [3:0] distance_i;
 reg turn_right_i;
 wire [11:0] yd,yr;
 reg [11:0] expected;
 integer errors=0,samples=0,w,k,d,j,source_bit;
 TopModule dut(.word_i(word_i),.distance_i(distance_i),.turn_right_i(turn_right_i),.word_o(yd));
 RefModule refm(.word_i(word_i),.distance_i(distance_i),.turn_right_i(turn_right_i),.word_o(yr));
 initial begin
   for(w=0;w<4096;w=w+1) for(k=0;k<16;k=k+1) for(d=0;d<2;d=d+1) begin
     word_i=w;distance_i=k;turn_right_i=d;
     // Independent bit-index permutation, not paired shifts.
     for(j=0;j<12;j=j+1) begin
       source_bit=(d ? j+k : j+24-k)%12;
       expected[j]=word_i[source_bit];
     end
     #1;
     if(yr!==expected) $fatal(1,"ORACLE_ERROR rotate12 w=%h k=%0d dir=%0d",word_i,k,d);
     samples=samples+1;
     if(yd!==expected) begin
       errors=errors+1;
       if(errors==1) $display("FIRST_MISMATCH word=%h distance=%0d right=%0d got=%h expected=%h",word_i,k,d,yd,expected);
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

"""Reproduce independent, original development fixtures. Never imported by the agent."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parent
FINISH = r'''
  final begin
    if(completed) begin
      $display("Hint: Total mismatched samples is %0d out of %0d samples",errors,samples);
      $display("Mismatches: %0d in %0d samples",errors,samples);
    end else $display("TIMEOUT fixture incomplete");
  end
  initial begin #1000000; $fatal(1,"TIMEOUT fixture watchdog"); end
endmodule
'''
TASKS = []

TASKS.append(dict(
 id="v4_01_rotate12",topic="非二次幂循环位移、零距离与大于字长的距离",
 prompt='''实现纯组合的 12 位循环移位器。接口必须保持为：
module TopModule(input [11:0] word_i, input [3:0] distance_i,
                 input turn_right_i, output [11:0] word_o);
distance_i 是无符号数 0..15，实际移动距离 k=distance_i 对 12 取余。
turn_right_i=0 时将 word_i 循环左移 k 位，=1 时循环右移 k 位。
移出一端的位按原顺序回到另一端，k=0 时 word_o=word_i。
不要增加时钟、寄存器或延迟。只提交完整可综合的 Verilog/SystemVerilog。''',
 code=r'''module TopModule(input [11:0] word_i,input [3:0] distance_i,
 input turn_right_i,output reg [11:0] word_o);
 reg [3:0] k;
 always @* begin
   k=(distance_i>=12)?distance_i-12:distance_i;
   if(k==0) word_o=word_i;
   else if(turn_right_i) word_o=(word_i>>k)|(word_i<<(12-k));
   else word_o=(word_i<<k)|(word_i>>(12-k));
 end
endmodule
''',
 mutate=("(word_i<<k)|(word_i>>(12-k))", "(word_i<<k)"),
 mutant="循环左移丢失高端回填位，普通逻辑移位替代循环移位",
 tb=r'''`timescale 1ns/1ps
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
'''+FINISH))

TASKS.append(dict(
 id="v4_02_signed_addsub6",topic="带符号加减、扩大中间值、上下界饱和",
 prompt='''实现 6 位二进制补码饱和加减器，纯组合逻辑。接口：
module TopModule(input signed [5:0] lhs_i, input signed [5:0] rhs_i,
                 input subtract_i, output signed [5:0] value_o, output clipped_o);
subtract_i=0 时数学结果 z=lhs_i+rhs_i，为 1 时 z=lhs_i-rhs_i。
若 z>31，value_o=31 且 clipped_o=1；若 z<-32，value_o=-32 且 clipped_o=1。
其余情况 value_o=z、clipped_o=0，包括结果恰为 -32 或 31。
内部必须保留足够位宽，不允许先在 6 位截断后再判断溢出。
只提交完整可综合的 Verilog/SystemVerilog。''',
 code=r'''module TopModule(input signed [5:0] lhs_i,input signed [5:0] rhs_i,
 input subtract_i,output reg signed [5:0] value_o,output reg clipped_o);
 reg signed [6:0] wide;
 always @* begin
   if(subtract_i) wide={lhs_i[5],lhs_i}-{rhs_i[5],rhs_i};
   else wide={lhs_i[5],lhs_i}+{rhs_i[5],rhs_i};
   clipped_o=1'b1;
   if(wide>7'sd31) value_o=6'sd31;
   else if(wide< -7'sd32) value_o=6'b100000;
   else begin value_o=wide[5:0];clipped_o=1'b0;end
 end
endmodule
''',
 mutate=("wide={lhs_i[5],lhs_i}-{rhs_i[5],rhs_i}","wide={lhs_i[5],lhs_i}+{rhs_i[5],rhs_i}"),
 mutant="减法选择被错误实现为加法，饱和框架仍可编译",
 tb=r'''`timescale 1ns/1ps
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
'''+FINISH))

TASKS.append(dict(
 id="v4_03_negedge_mod7",topic="下降沿采样、异步低有效复位、使能暂停与第七次脉冲",
 prompt='''实现如下计数模块，严格按下降沿采样：
module TopModule(input tick_i, input arst_ni, input clear_i, input advance_i,
                 output [2:0] position_o, output wrap_o);
arst_ni 是低有效异步复位，拉低后不等待时钟立即使 position_o=0、wrap_o=0。
正常情况下仅在 tick_i 的下降沿更新。优先级：clear_i > advance_i。
clear_i=1 时两个输出清零。否则 advance_i=1 时 position_o 以 0,1,2,3,4,5,6,0 循环；
仅从旧 position_o=6 更新到 0 的那个下降沿使 wrap_o=1，其他下降沿 wrap_o=0。
advance_i=0 时 position_o 保持、wrap_o=0。arst_ni 释放本身不得改变输出。
只提交完整可综合的 Verilog/SystemVerilog。''',
 code=r'''module TopModule(input tick_i,input arst_ni,input clear_i,input advance_i,
 output reg [2:0] position_o,output reg wrap_o);
 always @(negedge tick_i or negedge arst_ni) begin
   if(!arst_ni) begin position_o<=0;wrap_o<=0;end
   else if(clear_i) begin position_o<=0;wrap_o<=0;end
   else begin
     wrap_o<=0;
     if(advance_i) begin
       if(position_o==6) begin position_o<=0;wrap_o<=1;end
       else position_o<=position_o+1'b1;
     end
   end
 end
endmodule
''',
 mutate=("position_o==6", "position_o==5"),
 mutant="终值判断提前一次，将七次周期错误变成六次",
 tb=r'''`timescale 1ns/1ps
module tb;
 reg completed=0;
 reg tick_i=0,arst_ni=1,clear_i=0,advance_i=0;
 wire [2:0] pd,pr;
 wire wd,wr;
 integer errors=0,samples=0,i,n=0;
 reg pulse=0;
 reg [31:0] rng=32'h739a62b1;
 TopModule dut(.tick_i(tick_i),.arst_ni(arst_ni),.clear_i(clear_i),.advance_i(advance_i),.position_o(pd),.wrap_o(wd));
 RefModule refm(.tick_i(tick_i),.arst_ni(arst_ni),.clear_i(clear_i),.advance_i(advance_i),.position_o(pr),.wrap_o(wr));
 always #5 tick_i=~tick_i;
 task check;
   begin
     if({pr,wr}!=={n[2:0],pulse}) $fatal(1,"ORACLE_ERROR mod7 reset_n=%b clear=%b advance=%b ref=%d/%b expected=%0d/%b",arst_ni,clear_i,advance_i,pr,wr,n,pulse);
     samples=samples+1;
     if({pd,wd}!=={n[2:0],pulse}) begin
       errors=errors+1;
       if(errors==1) $display("FIRST_MISMATCH step=%0d reset_n=%b clear=%b advance=%b got=%d/%b expected=%0d/%b",samples,arst_ni,clear_i,advance_i,pd,wd,n,pulse);
     end
   end
 endtask
 task step(input r,c,e);
   begin
     @(posedge tick_i);arst_ni=r;clear_i=c;advance_i=e;
     if(!r) begin n=0;pulse=0;end
     #1;check;
     @(negedge tick_i);
     if(!r || c) begin n=0;pulse=0;end
     else begin pulse=e && (n==6);if(e) n=(n+1)%7;end
     #1;check;
   end
 endtask
 initial begin
   #1;advance_i=0;clear_i=0;arst_ni=0;n=0;pulse=0;#1;check;
   #1;arst_ni=1;#1;check;
   for(i=0;i<15;i=i+1) step(1,0,1);
   step(1,0,0);step(1,1,1);step(1,0,1);
   for(i=0;i<400;i=i+1) begin
     rng=1664525*rng+1013904223;
     step(rng[31:27]!=0,rng[26:23]==0,rng[7]);
   end
   // Assert reset between clock edges after producing nonzero state.
   step(1,1,0);step(1,0,1);
   #1;advance_i=0;clear_i=0;arst_ni=0;n=0;pulse=0;#1;check;
   #1;arst_ni=1;#1;check;
   step(1,0,0);completed=1;$finish;
 end
'''+FINISH))

TASKS.append(dict(
 id="v4_04_group_sum3",topic="非二次幂分组、当前输入包含在结果内、输出有效脉冲与暂停",
 prompt='''实现按每三个有效样本分组的求和器，接口如下：
module TopModule(input clk_i, input reset_i, input sample_valid_i,
                 input [4:0] sample_i, output [6:0] sum_o, output sum_valid_o);
所有状态在 clk_i 上升沿更新。reset_i 是高有效同步复位，优先于采样，复位时清空未完成组，sum_o=0，sum_valid_o=0。
每当 sample_valid_i=1，接收本拍无符号 sample_i。连续接收的每三个有效样本构成不重叠的一组；
接受第三个样本的同一个上升沿后，sum_o 更新为这三个样本之和（包含本拍输入），sum_valid_o=1。
其他上升沿 sum_valid_o=0，sum_o 保持最近已完成组的值。无效输入不改变未完成组的数量或和。
第三个样本完成后下一有效样本是新组第一个，无需空闲周期。只提交完整可综合 Verilog/SystemVerilog。''',
 code=r'''module TopModule(input clk_i,input reset_i,input sample_valid_i,
 input [4:0] sample_i,output reg [6:0] sum_o,output reg sum_valid_o);
 reg [1:0] phase;
 reg [6:0] partial_sum;
 always @(posedge clk_i) begin
   if(reset_i) begin phase<=0;partial_sum<=0;sum_o<=0;sum_valid_o<=0;end
   else begin
     sum_valid_o<=0;
     if(sample_valid_i) begin
       if(phase==2) begin
         sum_o<=partial_sum+{2'b00,sample_i};sum_valid_o<=1;
         partial_sum<=0;phase<=0;
       end else begin partial_sum<=partial_sum+{2'b00,sample_i};phase<=phase+1'b1;end
     end
   end
 end
endmodule
''',
 mutate=("sum_o<=partial_sum+{2'b00,sample_i}", "sum_o<=partial_sum"),
 mutant="接受第三个样本时只输出旧累计值，漏加当前输入",
 tb=r'''`timescale 1ns/1ps
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
'''+FINISH))

TASKS.append(dict(
 id="v4_05_enabled_1101",topic="重叠序列检测、使能暂停与脉冲清除",
 prompt='''实现允许重叠的串行序列 1101 检测器。接口：
module TopModule(input clock_i, input reset_i, input bit_enable_i,
                 input bit_i, output match_o);
仅在 clock_i 上升沿工作。reset_i 是高有效同步复位，复位优先，清除历史且 match_o=0。
未复位时，每个 bit_enable_i=1 的上升沿接收 bit_i，组成有效比特流。
如果包含本拍新比特的最近四个有效比特正好是按时间顺序的 1,1,0,1，则该沿后 match_o=1，否则为 0。
允许不同匹配共享比特；收满四个有效比特前 match_o 必须为 0。
bit_enable_i=0 时不改变历史，但该沿后 match_o=0，禁止把旧脉冲保持为 1。
只提交完整可综合的 Verilog/SystemVerilog。''',
 code=r'''module TopModule(input clock_i,input reset_i,input bit_enable_i,
 input bit_i,output reg match_o);
 reg [2:0] history;
 reg [1:0] seen;
 always @(posedge clock_i) begin
   if(reset_i) begin history<=0;seen<=0;match_o<=0;end
   else begin
     match_o<=0;
     if(bit_enable_i) begin
       match_o<=(seen==3 && history==3'b110 && bit_i);
       history<={history[1:0],bit_i};
       if(seen<3) seen<=seen+1'b1;
     end
   end
 end
endmodule
''',
 mutate=("match_o<=0;\n     if(bit_enable_i)", "match_o<=match_o;\n     if(bit_enable_i)"),
 mutant="暂停使能时保持上一拍 match 脉冲，不按规格清零",
 tb=r'''`timescale 1ns/1ps
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
'''+FINISH))

TASKS.append(dict(
 id="v4_06_readyvalid_fifo2",topic="ready/valid 握手、满时同拍替换、无直通与异步复位",
 prompt='''实现容量为两个 5 位字的 FIFO。接口必须为：
module TopModule(input clk_i, input reset_ni,
 input send_valid_i, input [4:0] send_data_i, output send_ready_o,
 input recv_ready_i, output recv_valid_o, output [4:0] recv_data_o);
reset_ni 是低有效异步复位，立即清空 FIFO。数据在 clk_i 上升沿传输。
组合输出：recv_valid_o=1 当且仅当 FIFO 非空；非空时 recv_data_o 是最早未取出的字，空时必须为 0。
recv_valid_o && recv_ready_i 表示本沿取出一个旧字。
send_ready_o=1 当且仅当当前未满，或本沿会取出一个旧字；send_valid_i && send_ready_o 表示接收一个新字。
上述两个握手都依据上升沿之前的状态和输入决定。满时可同拍取出旧头并接收新字；新字进入队尾。
空时即使 recv_ready_i=1，接收到的新字也只入队，不能本拍直通并被取走。
无握手时保持数据；复位释放本身不接收输入；不增加延迟、额外端口或修改接口。只提交可综合 Verilog/SystemVerilog。''',
 code=r'''module TopModule(input clk_i,input reset_ni,
 input send_valid_i,input [4:0] send_data_i,output send_ready_o,
 input recv_ready_i,output recv_valid_o,output [4:0] recv_data_o);
 reg [4:0] mem[0:1];
 reg head,tail;
 reg [1:0] used;
 wire take=recv_ready_i && recv_valid_o;
 wire put=send_valid_i && send_ready_o;
 assign recv_valid_o=(used!=0);
 assign recv_data_o=(used==0)?5'b0:mem[head];
 assign send_ready_o=(used<2)||take;
 always @(posedge clk_i or negedge reset_ni) begin
   if(!reset_ni) begin head<=0;tail<=0;used<=0;end
   else begin
     if(take) head<=~head;
     if(put) begin mem[tail]<=send_data_i;tail<=~tail;end
     case({put,take})
       2'b10:used<=used+1'b1;
       2'b01:used<=used-1'b1;
       default:used<=used;
     endcase
   end
 end
endmodule
''',
 mutate=("assign send_ready_o=(used<2)||take", "assign send_ready_o=(used<2)"),
 mutant="满时即使旧字被取出也拒绝新字，破坏同拍替换",
 tb=r'''`timescale 1ns/1ps
module tb;
 reg completed=0;
 reg clk_i=0,reset_ni=1,send_valid_i=0,recv_ready_i=0;
 reg [4:0] send_data_i=0;
 wire sd,sr,vd,vr;
 wire [4:0] dd,dr;
 integer errors=0,samples=0,i,n=0,head=0,tail=0;
 reg take,put,ready_expected,valid_expected;
 reg [4:0] data_expected;
 reg [4:0] queue[0:2047];
 reg [31:0] rng=32'h81c45a39;
 TopModule dut(.clk_i(clk_i),.reset_ni(reset_ni),.send_valid_i(send_valid_i),.send_data_i(send_data_i),.send_ready_o(sd),.recv_ready_i(recv_ready_i),.recv_valid_o(vd),.recv_data_o(dd));
 RefModule refm(.clk_i(clk_i),.reset_ni(reset_ni),.send_valid_i(send_valid_i),.send_data_i(send_data_i),.send_ready_o(sr),.recv_ready_i(recv_ready_i),.recv_valid_o(vr),.recv_data_o(dr));
 always #5 clk_i=~clk_i;
 task check;
   begin
     ready_expected=(n<2)||(recv_ready_i && n>0);
     valid_expected=(n>0);
     data_expected=(n==0)?5'b0:queue[head];
     if({sr,vr,dr}!=={ready_expected,valid_expected,data_expected}) $fatal(1,"ORACLE_ERROR fifo2 reset_n=%b send=%b take=%b in=%d ref=%b/%b/%d expected=%b/%b/%d",reset_ni,send_valid_i,recv_ready_i,send_data_i,sr,vr,dr,ready_expected,valid_expected,data_expected);
     samples=samples+1;
     if({sd,vd,dd}!=={ready_expected,valid_expected,data_expected}) begin
       errors=errors+1;
       if(errors==1) $display("FIRST_MISMATCH step=%0d reset_n=%b send_valid=%b recv_ready=%b in=%0d got=%b/%b/%0d expected=%b/%b/%0d",samples,reset_ni,send_valid_i,recv_ready_i,send_data_i,sd,vd,dd,ready_expected,valid_expected,data_expected);
     end
   end
 endtask
 task step(input r,s,t,input [4:0] d);
   begin
     @(negedge clk_i);reset_ni=r;send_valid_i=s;recv_ready_i=t;send_data_i=d;
     if(!r) begin n=0;head=0;tail=0;end
     #1;check;
     @(posedge clk_i);
     if(!r) begin n=0;head=0;tail=0;end
     else begin
       take=t && n>0;put=s && (n<2 || take);
       if(take) begin head=head+1;n=n-1;end
       if(put) begin queue[tail]=d;tail=tail+1;n=n+1;end
     end
     #1;check;
   end
 endtask
 initial begin
   #1;reset_ni=0;#1;check;#1;reset_ni=1;#1;check;
   step(1,0,1,0);step(1,1,1,7); // Empty cannot bypass a new word.
   step(1,1,0,11);step(1,1,0,31); // Full rejects a word with no take.
   step(1,1,1,19);step(1,1,1,23); // Full replacement in both pointer positions.
   step(1,0,1,0);step(1,0,1,0);step(1,0,1,0);
   for(i=0;i<600;i=i+1) begin
     rng=1664525*rng+1013904223;
     step(rng[31:27]!=0,rng[8],rng[7],rng[4:0]);
   end
   step(1,1,0,31);#1;send_valid_i=0;recv_ready_i=0;reset_ni=0;n=0;head=0;tail=0;#1;check;
   #1;reset_ni=1;#1;check;
   step(1,0,0,0);completed=1;$finish;
 end
'''+FINISH))


def main():
    refs,mutants={},{}
    for task in TASKS:
        task_id=task['id']
        prompt_dir=ROOT/'prompts'/task_id
        directory=ROOT/'evaluator'/'tasks'/task_id
        for path in (prompt_dir,directory/'reference',directory/'mutants'):
            path.mkdir(parents=True,exist_ok=True)
        (prompt_dir/'prompt.txt').write_text(task['prompt']+'\n',encoding='utf-8')
        (directory/'reference'/'solution.sv').write_text(task['code'],encoding='utf-8')
        (directory/'ref.sv').write_text(task['code'].replace('module TopModule(', 'module RefModule(',1),encoding='utf-8')
        old,new=task['mutate']
        assert old in task['code'], task_id
        (directory/'mutants'/'bug.sv').write_text(task['code'].replace(old,new,1),encoding='utf-8')
        (directory/'tb.sv').write_text(task['tb'],encoding='utf-8')
        config=dict(task_id=task_id,top='TopModule',tb_top='tb',part='xczu3eg-sbva484-1-e',period_ns=5,
                    reference='reference/solution.sv',reference_module='ref.sv',testbench='tb.sv',extra_files=[],
                    source='original_local_development_fixture',topic=task['topic'],deliberate_mutant=task['mutant'])
        (directory/'task.json').write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        refs[task_id]=f'tasks/{task_id}/reference/solution.sv'
        mutants[task_id]=f'tasks/{task_id}/mutants/bug.sv'
    for name,value in (('reference-manifest.json',refs),('mutants-manifest.json',mutants)):
        (ROOT/'evaluator'/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    inventory={}
    for path in sorted(ROOT.rglob('*')):
        if path.is_file() and path.name not in ('freeze-manifest.json',) and 'preflight' not in path.parts:
            content=path.read_bytes()
            inventory[path.relative_to(ROOT).as_posix()]=dict(bytes=len(content),sha256=hashlib.sha256(content).hexdigest())
    (ROOT/'freeze-manifest.json').write_text(json.dumps(dict(note='Frozen before V3/V4 model generation; development fixtures, not official hidden tests.',files=inventory),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'Created {len(TASKS)} tasks; frozen {len(inventory)} files.')


if __name__=='__main__':
    main()
